from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import threading
from typing import Iterable
from uuid import uuid4
import zipfile
import httpx
import chromadb

TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

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
        self._users_collection = None
        self._chat_messages_collection = None
        self._chunks_collection = None
        self._storage_ready = False
        self._db_dir = None

    def configure(self, database_url: str = "", sqlite_path: str = "data/documents.db") -> None:
        db_dir = Path(sqlite_path).parent / "chromadb"
        self._db_dir = db_dir

        db_dir.mkdir(parents=True, exist_ok=True)
        self._chroma_client = chromadb.PersistentClient(path=str(db_dir))
        
        # Get or create our collections
        self._users_collection = self._chroma_client.get_or_create_collection(
            name="users"
        )
        self._chat_messages_collection = self._chroma_client.get_or_create_collection(
            name="chat_messages"
        )
        self._chunks_collection = self._chroma_client.get_or_create_collection(
            name="document_chunks"
        )
        self._storage_ready = True

    def _upload_backup(self) -> None:
        pass

    def trigger_backup(self) -> None:
        # Runs backup asynchronously in a daemon thread so that API requests don't block
        threading.Thread(target=self._upload_backup, daemon=True).start()



    @property
    def storage_backend(self) -> str:
        return "chromadb"

    def create_user(self, first_name: str, last_name: str, email: str, phone_number: str, password_hash: str) -> dict:
        if self.get_user_by_email(email):
            raise ValueError("A user with this email already exists.")
        if self.get_user_by_phone(phone_number):
            raise ValueError("A user with this phone number already exists.")
        uid = str(uuid4())
        user_data = {
            "id": uid,
            "first_name": first_name,
            "last_name": last_name,
            "email": email.strip().lower(),
            "phone_number": phone_number,
            "is_verified": True,
            "created_at": utc_now(),
            "tokens_used": 0,
            "token_limit": 50000,
            "prompts_used_today": 0,
            "prompts_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "password_hash": password_hash
        }
        self._users_collection.add(
            ids=[uid],
            metadatas=[user_data],
            documents=[f"{first_name} {last_name} {email}"]
        )
        self.trigger_backup()
        return user_data
    def verify_user(self, email: str) -> None:
        user = self.get_user_by_email(email)
        if user:
            user["is_verified"] = True
            self._users_collection.update(
                ids=[user["id"]],
                metadatas=[user]
            )
            self.trigger_backup()

    def get_user_by_email(self, email: str) -> dict | None:
        if not self._storage_ready:
            self.configure()
        try:
            res = self._users_collection.get(where={"email": email.strip().lower()})
            if res and res["metadatas"]:
                meta = res["metadatas"][0]
                if "tokens_used" not in meta:
                    meta["tokens_used"] = 0
                if "token_limit" not in meta:
                    meta["token_limit"] = 50000
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if meta.get("prompts_date") != today:
                    meta["prompts_used_today"] = 0
                    meta["prompts_date"] = today
                return meta
        except Exception:
            pass
        return None

    def get_user_by_phone(self, phone_number: str) -> dict | None:
        if not self._storage_ready:
            self.configure()
        try:
            res = self._users_collection.get(where={"phone_number": phone_number})
            if res and res["metadatas"]:
                meta = res["metadatas"][0]
                if "tokens_used" not in meta:
                    meta["tokens_used"] = 0
                if "token_limit" not in meta:
                    meta["token_limit"] = 50000
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if meta.get("prompts_date") != today:
                    meta["prompts_used_today"] = 0
                    meta["prompts_date"] = today
                return meta
        except Exception:
            pass
        return None


    def get_user_by_id(self, user_id: str) -> dict | None:
        if not self._storage_ready:
            self.configure()
        try:
            res = self._users_collection.get(ids=[user_id])
            if res and res["metadatas"]:
                meta = res["metadatas"][0]
                if "tokens_used" not in meta:
                    meta["tokens_used"] = 0
                if "token_limit" not in meta:
                    meta["token_limit"] = 50000
                today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                if meta.get("prompts_date") != today:
                    meta["prompts_used_today"] = 0
                    meta["prompts_date"] = today
                return meta
        except Exception:
            pass
        return None

    def update_user_profile(self, uid: str, first_name: str, last_name: str, phone_number: str) -> None:
        existing = self.get_user_by_id(uid)
        if not existing:
            return
        existing["first_name"] = first_name
        existing["last_name"] = last_name
        existing["phone_number"] = phone_number
        self._users_collection.update(
            ids=[uid],
            metadatas=[existing],
            documents=[f"{first_name} {last_name} {existing.get('email', '')}"]
        )
        self.trigger_backup()

    def update_user_session(self, user_id: str, session_token: str) -> None:
        user = self.get_user_by_id(user_id)
        if not user:
            return
        user["active_session_token"] = session_token
        self._users_collection.update(
            ids=[user_id],
            metadatas=[user]
        )
        self.trigger_backup()

    def increment_user_tokens(self, user_id: str, tokens: int) -> dict | None:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        current_used = int(user.get("tokens_used", 0))
        new_used = current_used + tokens
        user["tokens_used"] = new_used
        self._users_collection.update(
            ids=[user_id],
            metadatas=[user]
        )
        self.trigger_backup()
        return user

    def increment_user_prompts(self, user_id: str) -> dict | None:
        user = self.get_user_by_id(user_id)
        if not user:
            return None
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if user.get("prompts_date") != today:
            user["prompts_used_today"] = 0
            user["prompts_date"] = today
        
        user["prompts_used_today"] = int(user.get("prompts_used_today", 0)) + 1
        self._users_collection.update(
            ids=[user_id],
            metadatas=[user]
        )
        self.trigger_backup()
        return user

    def get_user_file_count(self, user_id: str) -> int:
        if not self._storage_ready:
            self.configure()
        try:
            res = self._chunks_collection.get(where={"user_id": user_id})
            if not res or not res["ids"]:
                return 0
            filenames = set()
            for meta in res["metadatas"]:
                filenames.add(meta.get("filename"))
            return len(filenames)
        except Exception:
            return 0

    def add_chunks(self, user_id: str, filename: str, full_text: str, chunks: Iterable[Chunk]) -> int:
        incoming = list(chunks)
        if not incoming:
            return 0

        if not self._storage_ready:
            self.configure()

        existing = self._chunks_collection.get(where={"user_id": user_id})
        if existing and existing["ids"]:
            self._chunks_collection.delete(ids=existing["ids"])

        document_id = str(uuid4())
        ids = []
        documents = []
        metadatas = []
        
        for chunk in incoming:
            chunk_key = f"{user_id}_{document_id}_{chunk.chunk_id}"
            ids.append(chunk_key)
            documents.append(chunk.text)
            metadatas.append({
                "user_id": user_id,
                "document_id": document_id,
                "filename": filename,
                "chunk_id": chunk.chunk_id
            })

        self._chunks_collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        self.trigger_backup()
        return len(incoming)

    def clear_user_chunks(self, user_id: str) -> None:
        if not self._storage_ready:
            self.configure()
        existing = self._chunks_collection.get(where={"user_id": user_id})
        if existing and existing["ids"]:
            self._chunks_collection.delete(ids=existing["ids"])
            self.trigger_backup()

    def get_user_chunks(self, user_id: str) -> list[Chunk]:
        if not self._storage_ready:
            self.configure()
        try:
            res = self._chunks_collection.get(where={"user_id": user_id})
            if not res or not res["ids"]:
                return []
            chunk_objs = []
            for i in range(len(res["ids"])):
                meta = res["metadatas"][i]
                chunk_objs.append(
                    Chunk(
                        filename=meta["filename"],
                        chunk_id=meta["chunk_id"],
                        text=res["documents"][i],
                        tokens=tuple(),
                        user_id=meta["user_id"],
                        document_id=meta["document_id"]
                    )
                )
            return chunk_objs
        except Exception:
            return []

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

    def add_chat_message(self, user_id: str, role: str, content: str, sources: list[dict] | None = None, session_id: str = "default") -> None:
        if not self._storage_ready:
            self.configure()
        msg_id = str(uuid4())
        created_at = utc_now()
        self._chat_messages_collection.add(
            ids=[msg_id],
            documents=[content],
            metadatas=[{
                "user_id": user_id,
                "session_id": session_id,
                "role": role,
                "sources": json.dumps(sources or []),
                "created_at": created_at
            }]
        )
        self.trigger_backup()

    def get_chat_history(self, user_id: str, session_id: str = "default", limit: int = 50) -> list[dict]:
        if not self._storage_ready:
            self.configure()
        try:
            res = self._chat_messages_collection.get(
                where={"user_id": user_id}
            )
            if not res or not res["ids"]:
                return []

            items = []
            for i in range(len(res["ids"])):
                meta = res["metadatas"][i]
                if meta.get("session_id", "default") != session_id:
                    continue
                items.append({
                    "id": res["ids"][i],
                    "role": meta["role"],
                    "content": res["documents"][i],
                    "sources": json.loads(meta["sources"] or "[]"),
                    "created_at": meta["created_at"]
                })
            items.sort(key=lambda x: x["created_at"])
            return items[-limit:]
        except Exception as e:
            print(f"Error getting chat history: {e}")
            return []

    def get_chat_sessions(self, user_id: str) -> list[dict]:
        if not self._storage_ready:
            self.configure()
        try:
            res = self._chat_messages_collection.get(
                where={"user_id": user_id}
            )
            if not res or not res["ids"]:
                return []

            sessions = {}
            for i in range(len(res["ids"])):
                meta = res["metadatas"][i]
                sess_id = meta.get("session_id", "default")
                created_at = meta["created_at"]
                role = meta["role"]
                content = res["documents"][i]
                
                if sess_id not in sessions:
                    sessions[sess_id] = {
                        "session_id": sess_id,
                        "created_at": created_at,
                        "title": content[:40] + "..." if role == "user" else "New Chat",
                        "updated_at": created_at
                    }
                else:
                    if created_at < sessions[sess_id]["created_at"]:
                        sessions[sess_id]["created_at"] = created_at
                        if role == "user":
                            sessions[sess_id]["title"] = content[:40] + "..."
                    if created_at > sessions[sess_id]["updated_at"]:
                        sessions[sess_id]["updated_at"] = created_at
            
            items = list(sessions.values())
            items.sort(key=lambda x: x["updated_at"], reverse=True)
            return items
        except Exception as e:
            print(f"Error getting chat sessions: {e}")
            return []

store = DocumentStore()
