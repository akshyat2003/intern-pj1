from collections import Counter
from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterable

try:
    import psycopg
except ImportError:  # psycopg is only required when DATABASE_URL is configured.
    psycopg = None


TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


STOPWORDS = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are", "aren't", 
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but", "by", 
    "can't", "cannot", "could", "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", 
    "down", "during", "each", "few", "for", "from", "further", "had", "hadn't", "has", "hasn't", "have", 
    "haven't", "having", "he", "he'd", "he'll", "he's", "her", "here", "here's", "hers", "herself", 
    "him", "himself", "his", "how", "how's", "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", 
    "isn't", "it", "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my", "myself", 
    "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other", "ought", "our", "ours", 
    "ourselves", "out", "over", "own", "same", "shan't", "she", "she'd", "she'll", "she's", "should", 
    "shouldn't", "so", "some", "such", "than", "that", "that's", "the", "their", "theirs", "them", 
    "themselves", "then", "there", "there's", "these", "they", "they'd", "they'll", "they're", "they've", 
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was", "wasn't", "we", 
    "we'd", "we'll", "we're", "we've", "were", "weren't", "what", "what's", "when", "when's", "where", 
    "where's", "which", "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would", 
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours", "yourself", "yourselves"
}


@dataclass(frozen=True)
class Chunk:
    filename: str
    chunk_id: int
    text: str
    tokens: tuple[str, ...]


def tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_RE.finditer(text)]


def chunk_text(text: str, filename: str, chunk_size: int, overlap: int) -> list[Chunk]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []

    chunks: list[Chunk] = []
    start = 0
    chunk_id = 1
    step = max(1, chunk_size - overlap)

    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        if end < len(clean):
            boundary = clean.rfind(" ", start, end)
            if boundary > start + chunk_size // 2:
                end = boundary

        text_chunk = clean[start:end].strip()
        if text_chunk:
            chunks.append(
                Chunk(
                    filename=filename,
                    chunk_id=chunk_id,
                    text=text_chunk,
                    tokens=tuple(tokenize(text_chunk)),
                )
            )
            chunk_id += 1

        start += step

    return chunks


class DocumentStore:
    def __init__(self) -> None:
        self._chunks: list[Chunk] = []
        self._database_url = ""
        self._sqlite_path = Path("data/documents.db")
        self._storage_ready = False

    def configure(self, database_url: str = "", sqlite_path: str = "data/documents.db") -> None:
        self._database_url = database_url.strip()
        self._sqlite_path = Path(sqlite_path)
        self._ensure_storage()
        self._chunks = self._load_chunks()
        self._storage_ready = True

    @property
    def chunks(self) -> list[Chunk]:
        return self._chunks

    def add_chunks(self, chunks: Iterable[Chunk]) -> int:
        incoming = list(chunks)
        if not incoming:
            return 0
        
        if not self._storage_ready:
            self.configure()

        filename = incoming[0].filename
        self._chunks = [c for c in self._chunks if c.filename != filename]
        self._chunks.extend(incoming)
        self._replace_persisted_chunks(filename, incoming)
        return len(incoming)

    @property
    def storage_backend(self) -> str:
        return "postgres" if self._database_url else "sqlite"

    def _ensure_storage(self) -> None:
        if self._database_url:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL is set, but psycopg is not installed.")
            with psycopg.connect(self._database_url, autocommit=True) as connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS document_chunks (
                        filename TEXT NOT NULL,
                        chunk_id INTEGER NOT NULL,
                        text TEXT NOT NULL,
                        tokens TEXT NOT NULL,
                        PRIMARY KEY (filename, chunk_id)
                    )
                    """
                )
            return

        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._sqlite_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS document_chunks (
                    filename TEXT NOT NULL,
                    chunk_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    tokens TEXT NOT NULL,
                    PRIMARY KEY (filename, chunk_id)
                )
                """
            )

    def _load_chunks(self) -> list[Chunk]:
        if self._database_url:
            with psycopg.connect(self._database_url) as connection:
                rows = connection.execute(
                    "SELECT filename, chunk_id, text, tokens FROM document_chunks ORDER BY filename, chunk_id"
                ).fetchall()
        else:
            with sqlite3.connect(self._sqlite_path) as connection:
                rows = connection.execute(
                    "SELECT filename, chunk_id, text, tokens FROM document_chunks ORDER BY filename, chunk_id"
                ).fetchall()

        chunks: list[Chunk] = []
        for filename, chunk_id, text, tokens_json in rows:
            tokens = tuple(json.loads(tokens_json))
            chunks.append(Chunk(filename=filename, chunk_id=chunk_id, text=text, tokens=tokens))
        return chunks

    def _replace_persisted_chunks(self, filename: str, chunks: list[Chunk]) -> None:
        rows = [(chunk.filename, chunk.chunk_id, chunk.text, json.dumps(chunk.tokens)) for chunk in chunks]

        if self._database_url:
            with psycopg.connect(self._database_url, autocommit=True) as connection:
                connection.execute("DELETE FROM document_chunks WHERE filename = %s", (filename,))
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO document_chunks (filename, chunk_id, text, tokens)
                        VALUES (%s, %s, %s, %s)
                        """,
                        rows,
                    )
            return

        with sqlite3.connect(self._sqlite_path) as connection:
            connection.execute("DELETE FROM document_chunks WHERE filename = ?", (filename,))
            connection.executemany(
                """
                INSERT INTO document_chunks (filename, chunk_id, text, tokens)
                VALUES (?, ?, ?, ?)
                """,
                rows,
            )

    def search(self, query: str, limit: int) -> list[tuple[Chunk, float]]:
        query_tokens = tokenize(query)
        filtered_tokens = [t for t in query_tokens if t not in STOPWORDS]
        if filtered_tokens:
            query_tokens = filtered_tokens

        if not query_tokens or not self._chunks:
            return []

        query_counts = Counter(query_tokens)
        doc_freq: Counter[str] = Counter()
        for chunk in self._chunks:
            doc_freq.update(set(chunk.tokens))

        total_docs = len(self._chunks)
        avg_len = sum(len(chunk.tokens) for chunk in self._chunks) / total_docs
        k1 = 1.5
        b = 0.75
        scored: list[tuple[Chunk, float]] = []

        for chunk in self._chunks:
            token_counts = Counter(chunk.tokens)
            score = 0.0
            chunk_len = max(1, len(chunk.tokens))

            for token, query_count in query_counts.items():
                freq = token_counts[token]
                if freq == 0:
                    continue

                idf = math.log(1 + (total_docs - doc_freq[token] + 0.5) / (doc_freq[token] + 0.5))
                numerator = freq * (k1 + 1)
                denominator = freq + k1 * (1 - b + b * chunk_len / avg_len)
                score += idf * numerator / denominator * query_count

            if score > 0:
                scored.append((chunk, score))

        return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]


store = DocumentStore()
