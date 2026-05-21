import httpx
import re

from .config import Settings


SYSTEM_PROMPT = """You are a RAG chatbot. Answer only from the provided document context.
If the context does not contain the answer, say you do not know based on the uploaded files.
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


def generate_local_answer(question: str, context: str, reason: str | None = None) -> str:
    best_sentence = _best_context_sentence(question, context)
    prefix = f"Based on the uploaded files: {best_sentence}"
    if reason:
        prefix = f"{prefix}\n\nNote: hosted AI generation was skipped because {reason}."

    return prefix


async def generate_answer(settings: Settings, question: str, context: str) -> str:
    if not settings.provider_api_key:
        return generate_local_answer(question, context, f"{settings.normalized_provider.upper()}_API_KEY is not set")

    url = f"{settings.provider_base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.provider_model,
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Document context:\n{context}\n\nQuestion: {question}",
            },
        ],
    }
    headers = {
        "Authorization": f"Bearer {settings.provider_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        return generate_local_answer(question, context, f"the provider request failed: {exc}")

    if response.status_code >= 400:
        return generate_local_answer(
            question,
            context,
            f"the provider returned HTTP {response.status_code}. Check your API key and model in backend/.env",
        )

    data = response.json()
    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        return generate_local_answer(question, context, "the provider returned an unexpected response")
