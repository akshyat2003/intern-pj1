import os
import shutil
import zipfile
import threading
import json
import httpx
import chromadb
from pathlib import Path
from uuid import uuid4
from typing import Iterable, Sequence
from datetime import datetime, timezone

from .models import Chunk
from .llm_client import tokenize

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def zip_dir(dir_path: Path, zip_file_path: Path) -> None:
    with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(dir_path):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(dir_path)
                zipf.write(file_path, arcname)

def unzip_file(zip_file_path: Path, dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        zip_ref.extractall(dest_dir)

class DocumentStore:
    def __init__(self) -> None:
        self._chroma_client = None
        self._chunks_collection = None
        self._storage_ready = False
        self._db_dir = None

    def configure(self, database_url: str = "", sqlite_path: str = "data/documents.db") -> None:
        db_dir = Path(sqlite_path).parent / "chromadb"
        self._db_dir = db_dir

        # Configure SQLite database path
        from .database import db
        db.db_path = Path(sqlite_path)

        # Try to restore database from Supabase Storage
        supabase_url = os.getenv("SUPABASE_URL", "").strip()
        supabase_key = os.getenv("SUPABASE_KEY", "").strip()
        supabase_bucket = os.getenv("SUPABASE_BUCKET", "").strip()

        if supabase_url and supabase_key and supabase_bucket:
            db_dir.parent.mkdir(parents=True, exist_ok=True)
            zip_file = db_dir.parent / "chromadb.zip"
            url = f"{supabase_url}/storage/v1/object/authenticated/{supabase_bucket}/chromadb.zip"
            headers = {"Authorization": f"Bearer {supabase_key}"}
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    zip_file.write_bytes(resp.content)
                    
                    if db_dir.exists():
                        shutil.rmtree(db_dir)
                    sqlite_file = Path(sqlite_path)
                    if sqlite_file.exists():
                        sqlite_file.unlink()

                    unzip_file(zip_file, db_dir.parent)
                    zip_file.unlink(missing_ok=True)
                    print("Successfully restored backup from Supabase Storage.")
                else:
                    print(f"No existing backup found on Supabase (Status: {resp.status_code}).")
            except Exception as e:
                print(f"Error restoring backup: {e}")

        db_dir.mkdir(parents=True, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=str(db_dir))
        
        # Initialize SQLite tables
        db.initialize_tables()

        # Chroma DB collections
        self._chunks_collection = self._chroma_client.get_or_create_collection(
            name="document_chunks"
        )
        self._storage_ready = True

    def _upload_backup(self) -> None:
        supabase_url = os.getenv("SUPABASE_URL", "").strip()
        supabase_key = os.getenv("SUPABASE_KEY", "").strip()
        supabase_bucket = os.getenv("SUPABASE_BUCKET", "").strip()
        
        if not (supabase_url and supabase_key and supabase_bucket) or not self._storage_ready or not self._db_dir:
            return

        data_dir = self._db_dir.parent
        zip_file = data_dir / "chromadb_temp.zip"
        try:
            with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(data_dir):
                    for file in files:
                        if file.endswith(".zip"):
                            continue
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(data_dir)
                        zipf.write(file_path, arcname)

            url = f"{supabase_url}/storage/v1/object/{supabase_bucket}/chromadb.zip"
            headers = {
                "Authorization": f"Bearer {supabase_key}",
                "x-upsert": "true"
            }
            
            with open(zip_file, "rb") as f:
                with httpx.Client(timeout=60.0) as client:
                    resp = client.post(url, headers=headers, content=f)
                
            if resp.status_code == 200:
                print("Backup successfully synced to Supabase Storage.")
            else:
                print(f"Backup sync failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Error syncing backup to Supabase: {e}")
        finally:
            zip_file.unlink(missing_ok=True)

    def trigger_backup(self) -> None:
        threading.Thread(target=self._upload_backup, daemon=True).start()

    @property
    def chunks(self) -> list[Chunk]:
        from .database import db
        conn = db.get_connection()
        try:
            rows = conn.execute("""
                SELECT dc.*, d.file_name, d.user_id FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
            """).fetchall()
            chunk_objs = []
            for r in rows:
                chunk_objs.append(
                    Chunk(
                        filename=r["file_name"],
                        chunk_id=r["chunk_index"],
                        text=r["chunk_text"],
                        tokens=tuple(tokenize(r["chunk_text"])),
                        user_id=r["user_id"],
                        document_id=r["document_id"]
                    )
                )
            return chunk_objs
        except Exception:
            return []
        finally:
            conn.close()

    @property
    def storage_backend(self) -> str:
        return "sqlite+chromadb"

    def create_user(self, first_name: str, last_name: str, email: str, phone_number: str, password_hash: str) -> dict:
        from .database import db
        email_clean = email.strip().lower()
        if self.get_user_by_email(email_clean):
            raise ValueError("A user with this email already exists.")
        
        uid = str(uuid4())
        created_at = utc_now()
        
        conn = db.get_connection()
        try:
            conn.execute("""
                INSERT INTO users (id, first_name, last_name, email, phone_number, password_hash, created_at, subscription_plan, is_verified, tokens_used, token_limit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uid, first_name, last_name, email_clean, phone_number, password_hash, created_at, 'free', 0, 0, 50000))
            conn.commit()
        finally:
            conn.close()
            
        self.trigger_backup()
        return self.get_user_by_id(uid)

    def verify_user(self, email: str) -> None:
        from .database import db
        conn = db.get_connection()
        try:
            conn.execute("UPDATE users SET is_verified = 1 WHERE email = ?", (email.strip().lower(),))
            conn.commit()
        finally:
            conn.close()
        self.trigger_backup()

    def get_user_by_email(self, email: str) -> dict | None:
        from .database import db
        conn = db.get_connection()
        try:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
            if row:
                user = dict(row)
                user["is_verified"] = bool(user["is_verified"])
                return user
        finally:
            conn.close()
        return None

    def get_user_by_id(self, user_id: str) -> dict | None:
        from .database import db
        conn = db.get_connection()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            if row:
                user = dict(row)
                user["is_verified"] = bool(user["is_verified"])
                return user
        finally:
            conn.close()
        return None

    def update_user_profile(self, uid: str, first_name: str, last_name: str, phone_number: str) -> None:
        from .database import db
        conn = db.get_connection()
        try:
            conn.execute("""
                UPDATE users SET first_name = ?, last_name = ?, phone_number = ? WHERE id = ?
            """, (first_name, last_name, phone_number, uid))
            conn.commit()
        finally:
            conn.close()
        self.trigger_backup()

    def increment_user_tokens(self, user_id: str, tokens: int) -> dict | None:
        from .database import db
        conn = db.get_connection()
        try:
            conn.execute("""
                UPDATE users SET tokens_used = tokens_used + ? WHERE id = ?
            """, (tokens, user_id))
            conn.commit()
        finally:
            conn.close()
        self.trigger_backup()
        return self.get_user_by_id(user_id)

    def save_otp(self, email: str, otp_hash: str, expires_at: str) -> None:
        from .database import db
        conn = db.get_connection()
        try:
            conn.execute("""
                INSERT INTO otps (email, otp_hash, expires_at, attempts)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(email) DO UPDATE SET otp_hash = excluded.otp_hash, expires_at = excluded.expires_at, attempts = 0
            """, (email.strip().lower(), otp_hash, expires_at))
            conn.commit()
        finally:
            conn.close()

    def get_otp(self, email: str) -> dict | None:
        from .database import db
        conn = db.get_connection()
        try:
            row = conn.execute("SELECT * FROM otps WHERE email = ?", (email.strip().lower(),)).fetchone()
            if row:
                return dict(row)
        finally:
            conn.close()
        return None

    def increment_otp_attempts(self, email: str) -> int:
        from .database import db
        conn = db.get_connection()
        try:
            conn.execute("UPDATE otps SET attempts = attempts + 1 WHERE email = ?", (email.strip().lower(),))
            conn.commit()
            row = conn.execute("SELECT attempts FROM otps WHERE email = ?", (email.strip().lower(),)).fetchone()
            if row:
                return row["attempts"]
        finally:
            conn.close()
        return 0

    def delete_otp(self, email: str) -> None:
        from .database import db
        conn = db.get_connection()
        try:
            conn.execute("DELETE FROM otps WHERE email = ?", (email.strip().lower(),))
            conn.commit()
        finally:
            conn.close()

    def add_chunks(self, user_id: str, filename: str, full_text: str, chunks: Iterable[Chunk]) -> int:
        incoming = list(chunks)
        if not incoming:
            return 0

        from .database import db
        conn = db.get_connection()
        
        try:
            existing_doc = conn.execute(
                "SELECT id FROM documents WHERE user_id = ? AND file_name = ?",
                (user_id, filename)
            ).fetchone()
            if existing_doc:
                doc_id = existing_doc["id"]
                conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                conn.commit()
        except Exception as e:
            print(f"Error checking existing documents: {e}")

        if not self._storage_ready:
            self.configure()

        try:
            existing_chroma = self._chunks_collection.get(where={"user_id": user_id})
            if existing_chroma and existing_chroma["ids"]:
                to_delete = []
                for i in range(len(existing_chroma["ids"])):
                    if existing_chroma["metadatas"][i].get("filename") == filename:
                        to_delete.append(existing_chroma["ids"][i])
                if to_delete:
                    self._chunks_collection.delete(ids=to_delete)
        except Exception as e:
            print(f"Error deleting old chunks from ChromaDB: {e}")

        doc_uuid = str(uuid4())
        uploaded_at = utc_now()
        
        try:
            conn.execute(
                "INSERT INTO documents (id, user_id, file_name, uploaded_at, status) VALUES (?, ?, ?, ?, ?)",
                (doc_uuid, user_id, filename, uploaded_at, "processed")
            )
            conn.commit()
        except Exception as e:
            print(f"Error inserting document: {e}")

        chroma_ids = []
        chroma_documents = []
        chroma_metadatas = []

        try:
            for chunk in incoming:
                chunk_uuid = str(uuid4())
                chunk_key = f"{user_id}_{doc_uuid}_{chunk.chunk_id}"
                
                conn.execute("""
                    INSERT INTO document_chunks (id, document_id, chunk_text, chunk_index, metadata)
                    VALUES (?, ?, ?, ?, ?)
                """, (chunk_uuid, doc_uuid, chunk.text, chunk.chunk_id, json.dumps({
                    "page_number": chunk.chunk_id
                })))
                
                chroma_ids.append(chunk_key)
                chroma_documents.append(chunk.text)
                chroma_metadatas.append({
                    "user_id": user_id,
                    "document_id": doc_uuid,
                    "filename": filename,
                    "chunk_id": chunk.chunk_id
                })
                
            conn.commit()
        except Exception as e:
            print(f"Error inserting chunks to SQLite: {e}")
        finally:
            conn.close()

        try:
            self._chunks_collection.add(
                ids=chroma_ids,
                documents=chroma_documents,
                metadatas=chroma_metadatas
            )
        except Exception as e:
            print(f"Error adding chunks to ChromaDB: {e}")

        self.trigger_backup()
        return len(incoming)

    def get_user_chunks(self, user_id: str) -> list[dict]:
        from .database import db
        conn = db.get_connection()
        try:
            rows = conn.execute("""
                SELECT dc.* FROM document_chunks dc
                JOIN documents d ON dc.document_id = d.id
                WHERE d.user_id = ?
            """, (user_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def search(self, user_id: str, query: str, limit: int) -> list[tuple[Chunk, float]]:
        if not self._storage_ready:
            self.configure()

        try:
            res = self._chunks_collection.query(
                query_texts=[query],
                n_results=limit,
                where={"user_id": user_id}
            )

            if not res or not res["ids"] or not res["ids"][0]:
                return []

            results = []
            for i in range(len(res["ids"][0])):
                meta = res["metadatas"][0][i]
                doc = res["documents"][0][i]
                distance = res["distances"][0][i] if res["distances"] else 0.0
                score = 1.0 / (1.0 + distance)

                chunk = Chunk(
                    filename=meta["filename"],
                    chunk_id=meta["chunk_id"],
                    text=doc,
                    tokens=tuple(tokenize(doc)),
                    user_id=meta["user_id"],
                    document_id=meta["document_id"]
                )
                results.append((chunk, score))
            return results
        except Exception as e:
            print(f"Error querying Chroma DB: {e}")
            return []

    def _get_or_create_default_chat(self, user_id: str) -> str:
        from .database import db
        conn = db.get_connection()
        try:
            row = conn.execute("SELECT id FROM chats WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
            if row:
                return row["id"]
            
            chat_id = str(uuid4())
            conn.execute(
                "INSERT INTO chats (id, user_id, title, created_at) VALUES (?, ?, ?, ?)",
                (chat_id, user_id, "Main Chat", utc_now())
            )
            conn.commit()
            return chat_id
        finally:
            conn.close()

    def add_chat_message(self, user_id: str, role: str, content: str, sources: list[dict] | None = None) -> None:
        from .database import db
        chat_id = self._get_or_create_default_chat(user_id)
        msg_id = str(uuid4())
        timestamp = utc_now()
        
        conn = db.get_connection()
        try:
            conn.execute("""
                INSERT INTO messages (id, chat_id, role, content, timestamp, token_count, sources)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (msg_id, chat_id, role, content, timestamp, 0, json.dumps(sources or [])))
            conn.commit()
        finally:
            conn.close()
        self.trigger_backup()

    def get_chat_history(self, user_id: str, limit: int = 50) -> list[dict]:
        from .database import db
        chat_id = self._get_or_create_default_chat(user_id)
        
        conn = db.get_connection()
        try:
            rows = conn.execute("""
                SELECT id, role, content, timestamp as created_at, sources FROM messages
                WHERE chat_id = ?
                ORDER BY timestamp ASC
            """, (chat_id,)).fetchall()
            
            items = []
            for row in rows:
                items.append({
                    "id": row["id"],
                    "role": row["role"],
                    "content": row["content"],
                    "sources": json.loads(row["sources"] or "[]"),
                    "created_at": row["created_at"]
                })
            return items[-limit:]
        except Exception as e:
            print(f"Error getting chat history: {e}")
            return []
        finally:
            conn.close()

    def log_retrieval(self, user_id: str, query: str, retrieved_chunk_ids: list[str], response: str, latency: float) -> None:
        from .database import db
        log_id = str(uuid4())
        created_at = utc_now()
        conn = db.get_connection()
        try:
            conn.execute("""
                INSERT INTO retrieval_logs (id, user_id, query, retrieved_chunk_ids, response, latency, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (log_id, user_id, query, json.dumps(retrieved_chunk_ids), response, latency, created_at))
            conn.commit()
        except Exception as e:
            print(f"Error logging retrieval: {e}")
        finally:
            conn.close()

store = DocumentStore()
