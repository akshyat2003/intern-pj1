import re
import os
from dotenv import load_dotenv
import litellm

from .config import Settings

load_dotenv()

SYSTEM_PROMPT = """You are a highly advanced RAG chatbot. STRICTLY base your answers ONLY on the provided document context.
If the context does not contain the answer, you MUST say "I do not know based on the uploaded files." Do NOT invent, guess, or use any pre-existing knowledge.
You MUST format your responses using rich Markdown.
IMPORTANT: When explaining processes, hierarchies, or comparisons, you MUST include a Mermaid.js diagram inside a ```mermaid code block. Be highly visual!
CRITICAL MERMAID RULES:
- ALWAYS enclose node text in double quotes if it contains spaces, parentheses, or special characters (e.g., A["Label (Info)"]).
- DO NOT use HTML tags or Markdown formatting inside node labels.
- For edge labels, strictly use `A -->|text| B` or `A --> B`. Never use invalid syntax like `-->|text|>`.
- Ensure correct and valid Mermaid syntax to prevent rendering errors.
Be concise and cite source filenames when useful."""


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _tokens(text: str) -> set[str]:
    stopwords = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is", "it", "of", "on", "or", "the", "to", "what", "when", "where", "which", "who", "why", "how"}
    return {token.lower() for token in TOKEN_RE.findall(text) if token.lower() not in stopwords}


def _best_context_sentence(question: str, context: str) -> str:
    question_tokens = _tokens(question)
    text_lines = [line for line in context.splitlines() if not line.startswith("[") and not line.startswith("Source:")]
    sentences = [sentence.strip() for sentence in SENTENCE_RE.split(" ".join(text_lines)) if sentence.strip()]
    if not sentences:
        return context

    def score(sentence: str) -> int:
        return len(_tokens(sentence) & question_tokens)

    best = max(sentences, key=score)
    return best if score(best) > 0 else sentences[0]



def estimate_tokens(text: str) -> int:
    words = len(re.findall(r"\w+", text))
    char_count = len(text)
    est_words = int(words * 1.3)
    est_chars = char_count // 4
    return max(1, (est_words + est_chars) // 2)


def estimate_prompt_tokens(question: str, context: str) -> int:
    prompt = f"{SYSTEM_PROMPT}\n\nDocument context:\n{context}\n\nQuestion: {question}"
    return estimate_tokens(prompt)


def generate_local_answer(question: str, context: str, reason: str | None = None) -> str:
    best_sentence = _best_context_sentence(question, context)
    prefix = f"Based on the uploaded files: {best_sentence}"
    if reason:
        prefix = f"{prefix}\n\nNote: hosted AI generation was skipped because {reason}."

    return prefix


async def generate_answer(settings: Settings, question: str, context: str, model: str | None = None) -> tuple[str, int, int]:
    selected_model = model or settings.provider_model
    
    # Smart Auto Model Selection
    if selected_model == "auto":
        q_lower = question.lower()
        complex_keywords = ["analyze", "compare", "synthesize", "code", "explain", "detail"]
        
        if len(context) > 20000:
            # Huge context -> Gemini 1.5 Pro is best suited
            selected_model = "gemini/gemini-1.5-pro"
        elif any(k in q_lower for k in complex_keywords):
            # Complex reasoning -> Claude 3.5 Sonnet or GPT-4o
            selected_model = "anthropic/claude-3-5-sonnet-20241022"
        else:
            # Fast, simple queries -> Groq Llama 3.1
            selected_model = "groq/llama-3.1-8b-instant"

    # Map litellm prefix for DeepSeek if they passed just deepseek-chat
    if selected_model == "deepseek-chat":
        selected_model = "deepseek/deepseek-chat"
        
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Document context:\n{context}\n\nQuestion: {question}"},
    ]

    try:
        response = await litellm.acompletion(
            model=selected_model,
            messages=messages,
            temperature=0.2,
        )
        answer = response.choices[0].message.content.strip()
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        
        if not prompt_tokens:
            prompt_tokens = estimate_prompt_tokens(question, context)
        if not completion_tokens:
            completion_tokens = estimate_tokens(answer)
            
        return answer, prompt_tokens, completion_tokens

    except Exception as exc:
        answer = generate_local_answer(question, context, f"the provider request failed: {exc}")
        p_tokens = estimate_prompt_tokens(question, context)
        c_tokens = estimate_tokens(answer)
        return answer, p_tokens, c_tokens


