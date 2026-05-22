from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterable
from uuid import uuid4

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # psycopg is only required when DATABASE_URL is configured.
    psycopg = None
    dict_row = None


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
    user_id: str = ""
    document_id: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
            chunks.append(Chunk(filename=filename, chunk_id=chunk_id, text=text_chunk, tokens=tuple(tokenize(text_chunk))))
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

    @property
    def storage_backend(self) -> str:
        return "postgres" if self._database_url else "sqlite"

    def create_user(self, first_name: str, last_name: str, email: str, phone_number: str, password_hash: str) -> dict:
        existing = self.get_user_by_email(email)
        if existing and existing["is_verified"]:
            raise ValueError("An account with this email already exists.")

        user_id = existing["id"] if existing else str(uuid4())
        params = {
            "id": user_id,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone_number": phone_number,
            "password_hash": password_hash,
            "is_verified": False,
            "created_at": existing["created_at"] if existing else utc_now(),
        }

        if self._database_url:
            self._execute(
                """
                INSERT INTO users (id, first_name, last_name, email, phone_number, password_hash, is_verified, created_at)
                VALUES (%(id)s, %(first_name)s, %(last_name)s, %(email)s, %(phone_number)s, %(password_hash)s, %(is_verified)s, %(created_at)s)
                ON CONFLICT (email) DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    phone_number = EXCLUDED.phone_number,
                    password_hash = EXCLUDED.password_hash,
                    is_verified = FALSE
                """,
                params,
            )
        else:
            self._execute(
                """
                INSERT INTO users (id, first_name, last_name, email, phone_number, password_hash, is_verified, created_at)
                VALUES (:id, :first_name, :last_name, :email, :phone_number, :password_hash, :is_verified, :created_at)
                ON CONFLICT(email) DO UPDATE SET
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    phone_number = excluded.phone_number,
                    password_hash = excluded.password_hash,
                    is_verified = 0
                """,
                params,
            )
        return self.get_user_by_email(email)

    def verify_user(self, email: str) -> None:
        self._execute("UPDATE users SET is_verified = TRUE WHERE email = %(email)s" if self._database_url else "UPDATE users SET is_verified = 1 WHERE email = :email", {"email": email})

    def get_user_by_email(self, email: str) -> dict | None:
        return self._fetch_one("SELECT * FROM users WHERE email = %(email)s" if self._database_url else "SELECT * FROM users WHERE email = :email", {"email": email})

    def get_user_by_id(self, user_id: str) -> dict | None:
        return self._fetch_one("SELECT * FROM users WHERE id = %(id)s" if self._database_url else "SELECT * FROM users WHERE id = :id", {"id": user_id})

    def save_otp(self, email: str, otp_hash: str, expires_at: str) -> None:
        if self._database_url:
            query = """
                INSERT INTO email_otps (email, otp_hash, expires_at, created_at)
                VALUES (%(email)s, %(otp_hash)s, %(expires_at)s, %(created_at)s)
                ON CONFLICT (email) DO UPDATE SET
                    otp_hash = EXCLUDED.otp_hash,
                    expires_at = EXCLUDED.expires_at,
                    created_at = EXCLUDED.created_at
            """
        else:
            query = """
                INSERT INTO email_otps (email, otp_hash, expires_at, created_at)
                VALUES (:email, :otp_hash, :expires_at, :created_at)
                ON CONFLICT(email) DO UPDATE SET
                    otp_hash = excluded.otp_hash,
                    expires_at = excluded.expires_at,
                    created_at = excluded.created_at
            """
        self._execute(query, {"email": email, "otp_hash": otp_hash, "expires_at": expires_at, "created_at": utc_now()})

    def get_otp(self, email: str) -> dict | None:
        return self._fetch_one("SELECT * FROM email_otps WHERE email = %(email)s" if self._database_url else "SELECT * FROM email_otps WHERE email = :email", {"email": email})

    def delete_otp(self, email: str) -> None:
        self._execute("DELETE FROM email_otps WHERE email = %(email)s" if self._database_url else "DELETE FROM email_otps WHERE email = :email", {"email": email})

    def add_chunks(self, user_id: str, filename: str, full_text: str, chunks: Iterable[Chunk]) -> int:
        incoming = list(chunks)
        if not incoming:
            return 0

        if not self._storage_ready:
            self.configure()

        document_id = str(uuid4())
        stored_chunks = [
            Chunk(
                filename=filename,
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                tokens=chunk.tokens,
                user_id=user_id,
                document_id=document_id,
            )
            for chunk in incoming
        ]

        self._replace_persisted_document(user_id, document_id, filename, full_text, stored_chunks)
        self._chunks = [chunk for chunk in self._chunks if not (chunk.user_id == user_id and chunk.filename == filename)]
        self._chunks.extend(stored_chunks)
        return len(stored_chunks)

    def search(self, user_id: str, query: str, limit: int) -> list[tuple[Chunk, float]]:
        query_tokens = tokenize(query)
        filtered_tokens = [t for t in query_tokens if t not in STOPWORDS]
        if filtered_tokens:
            query_tokens = filtered_tokens

        user_chunks = [chunk for chunk in self._chunks if chunk.user_id == user_id]
        if not query_tokens or not user_chunks:
            return []

        query_counts = Counter(query_tokens)
        doc_freq: Counter[str] = Counter()
        for chunk in user_chunks:
            doc_freq.update(set(chunk.tokens))

        total_docs = len(user_chunks)
        avg_len = sum(len(chunk.tokens) for chunk in user_chunks) / total_docs
        k1 = 1.5
        b = 0.75
        scored: list[tuple[Chunk, float]] = []

        for chunk in user_chunks:
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

    def add_chat_message(self, user_id: str, role: str, content: str, sources: list[dict] | None = None) -> None:
        params = {
            "id": str(uuid4()),
            "user_id": user_id,
            "role": role,
            "content": content,
            "sources": json.dumps(sources or []),
            "created_at": utc_now(),
        }
        if self._database_url:
            query = """
                INSERT INTO chat_messages (id, user_id, role, content, sources, created_at)
                VALUES (%(id)s, %(user_id)s, %(role)s, %(content)s, %(sources)s, %(created_at)s)
            """
        else:
            query = """
                INSERT INTO chat_messages (id, user_id, role, content, sources, created_at)
                VALUES (:id, :user_id, :role, :content, :sources, :created_at)
            """
        self._execute(query, params)

    def get_chat_history(self, user_id: str, limit: int = 50) -> list[dict]:
        query = (
            "SELECT id, role, content, sources, created_at FROM chat_messages WHERE user_id = %(user_id)s ORDER BY created_at DESC LIMIT %(limit)s"
            if self._database_url
            else "SELECT id, role, content, sources, created_at FROM chat_messages WHERE user_id = :user_id ORDER BY created_at DESC LIMIT :limit"
        )
        rows = self._fetch_all(query, {"user_id": user_id, "limit": limit})
        rows.reverse()
        for row in rows:
            row["sources"] = json.loads(row["sources"] or "[]")
        return rows

    def _ensure_storage(self) -> None:
        self._reset_legacy_document_chunks_if_needed()
        statements = [
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone_number TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                is_verified BOOLEAN NOT NULL DEFAULT FALSE,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS email_otps (
                email TEXT PRIMARY KEY,
                otp_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                extracted_text TEXT NOT NULL,
                total_chunks INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS document_chunks (
                user_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                text TEXT NOT NULL,
                tokens TEXT NOT NULL,
                PRIMARY KEY (user_id, document_id, chunk_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                sources TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """,
        ]

        if self._database_url:
            if psycopg is None:
                raise RuntimeError("DATABASE_URL is set, but psycopg is not installed.")
            with psycopg.connect(self._database_url, autocommit=True) as connection:
                for statement in statements:
                    connection.execute(statement)
            return

        self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._sqlite_path) as connection:
            for statement in statements:
                connection.execute(statement)

    def _reset_legacy_document_chunks_if_needed(self) -> None:
        if self._database_url:
            if psycopg is None:
                return
            with psycopg.connect(self._database_url, autocommit=True) as connection:
                exists = connection.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_name = 'document_chunks'
                    """
                ).fetchone()
                if not exists:
                    return
                user_id_column = connection.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'document_chunks' AND column_name = 'user_id'
                    """
                ).fetchone()
                if not user_id_column:
                    connection.execute("DROP TABLE document_chunks")
            return

        if not self._sqlite_path.exists():
            return
        with sqlite3.connect(self._sqlite_path) as connection:
            exists = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'document_chunks'"
            ).fetchone()
            if not exists:
                return
            columns = [row[1] for row in connection.execute("PRAGMA table_info(document_chunks)").fetchall()]
            if "user_id" not in columns:
                connection.execute("DROP TABLE document_chunks")

    def _load_chunks(self) -> list[Chunk]:
        rows = self._fetch_all("SELECT user_id, document_id, filename, chunk_id, text, tokens FROM document_chunks ORDER BY filename, chunk_id")
        chunks: list[Chunk] = []
        for row in rows:
            tokens = tuple(json.loads(row["tokens"]))
            chunks.append(
                Chunk(
                    filename=row["filename"],
                    chunk_id=row["chunk_id"],
                    text=row["text"],
                    tokens=tokens,
                    user_id=row["user_id"],
                    document_id=row["document_id"],
                )
            )
        return chunks

    def _replace_persisted_document(self, user_id: str, document_id: str, filename: str, full_text: str, chunks: list[Chunk]) -> None:
        chunk_rows = [
            {
                "user_id": user_id,
                "document_id": document_id,
                "filename": chunk.filename,
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "tokens": json.dumps(chunk.tokens),
            }
            for chunk in chunks
        ]
        document = {
            "id": document_id,
            "user_id": user_id,
            "filename": filename,
            "extracted_text": full_text,
            "total_chunks": len(chunks),
            "created_at": utc_now(),
        }

        if self._database_url:
            with psycopg.connect(self._database_url, autocommit=True) as connection:
                connection.execute("DELETE FROM documents WHERE user_id = %s AND filename = %s", (user_id, filename))
                connection.execute("DELETE FROM document_chunks WHERE user_id = %s AND filename = %s", (user_id, filename))
                connection.execute(
                    """
                    INSERT INTO documents (id, user_id, filename, extracted_text, total_chunks, created_at)
                    VALUES (%(id)s, %(user_id)s, %(filename)s, %(extracted_text)s, %(total_chunks)s, %(created_at)s)
                    """,
                    document,
                )
                with connection.cursor() as cursor:
                    cursor.executemany(
                        """
                        INSERT INTO document_chunks (user_id, document_id, filename, chunk_id, text, tokens)
                        VALUES (%(user_id)s, %(document_id)s, %(filename)s, %(chunk_id)s, %(text)s, %(tokens)s)
                        """,
                        chunk_rows,
                    )
            return

        with sqlite3.connect(self._sqlite_path) as connection:
            connection.execute("DELETE FROM documents WHERE user_id = ? AND filename = ?", (user_id, filename))
            connection.execute("DELETE FROM document_chunks WHERE user_id = ? AND filename = ?", (user_id, filename))
            connection.execute(
                """
                INSERT INTO documents (id, user_id, filename, extracted_text, total_chunks, created_at)
                VALUES (:id, :user_id, :filename, :extracted_text, :total_chunks, :created_at)
                """,
                document,
            )
            connection.executemany(
                """
                INSERT INTO document_chunks (user_id, document_id, filename, chunk_id, text, tokens)
                VALUES (:user_id, :document_id, :filename, :chunk_id, :text, :tokens)
                """,
                chunk_rows,
            )

    def _execute(self, query: str, params: dict | None = None) -> None:
        if self._database_url:
            with psycopg.connect(self._database_url, autocommit=True) as connection:
                connection.execute(query, params or {})
            return

        with sqlite3.connect(self._sqlite_path) as connection:
            connection.execute(query, params or {})

    def _fetch_one(self, query: str, params: dict | None = None) -> dict | None:
        rows = self._fetch_all(query, params)
        return rows[0] if rows else None

    def _fetch_all(self, query: str, params: dict | None = None) -> list[dict]:
        if self._database_url:
            with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
                rows = connection.execute(query, params or {}).fetchall()
                return [dict(row) for row in rows]

        with sqlite3.connect(self._sqlite_path) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(query, params or {}).fetchall()
            return [dict(row) for row in rows]


store = DocumentStore()
