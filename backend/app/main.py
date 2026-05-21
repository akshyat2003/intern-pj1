from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .document_store import chunk_text, store
from .file_loader import extract_text
from .llm_client import generate_answer
from .models import ChatRequest, ChatResponse, SourceChunk, UploadResponse


app = FastAPI(title="RAG Chatbot API")

settings = get_settings()
store.configure(settings.database_url, settings.sqlite_path)
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=settings.allowed_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | int]:
    return {"status": "ok", "chunks": len(store.chunks), "storage": store.storage_backend}


@app.post("/upload", response_model=UploadResponse)
async def upload_file(file: UploadFile = File(...)) -> UploadResponse:
    settings = get_settings()
    filename = file.filename or "uploaded-file"

    try:
        text = await extract_text(file)
        chunks = chunk_text(text, filename, settings.chunk_size, settings.chunk_overlap)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read file: {exc}") from exc

    if not chunks:
        raise HTTPException(status_code=400, detail="No readable text was found in this file.")

    added = store.add_chunks(chunks)
    return UploadResponse(filename=filename, chunks_added=added, total_chunks=len(store.chunks))


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is required.")

    results = store.search(question, settings.max_context_chunks)
    if not results:
        return ChatResponse(
            answer="I do not know based on the uploaded files. Upload a relevant document first.",
            sources=[],
        )

    context_parts = [
        f"[{index}] Source: {chunk.filename}, chunk {chunk.chunk_id}\n{chunk.text}"
        for index, (chunk, _score) in enumerate(results, start=1)
    ]
    context = "\n\n".join(context_parts)

    try:
        answer = await generate_answer(settings, question, context)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sources = [
        SourceChunk(filename=chunk.filename, chunk_id=chunk.chunk_id, text=chunk.text, score=round(score, 4))
        for chunk, score in results
    ]
    return ChatResponse(answer=answer, sources=sources)
