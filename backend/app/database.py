import sqlite3
import json
from pathlib import Path

class Database:
    def __init__(self, db_path: str = "data/documents.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def initialize_tables(self) -> None:
        conn = self.get_connection()
        cursor = conn.cursor()

        # 1. Users Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            phone_number TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT,
            subscription_plan TEXT DEFAULT 'free',
            is_verified BOOLEAN DEFAULT 0,
            api_key TEXT,
            tokens_used INTEGER DEFAULT 0,
            token_limit INTEGER DEFAULT 50000
        );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")

        # 2. Chats Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # 3. Messages Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            token_count INTEGER DEFAULT 0,
            sources TEXT DEFAULT '[]',
            FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
        );
        """)

        # 4. Documents Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            file_name TEXT NOT NULL,
            source_url TEXT,
            uploaded_at TEXT NOT NULL,
            status TEXT DEFAULT 'processed',
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        """)

        # 5. Document Chunks Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_text TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            metadata TEXT DEFAULT '{}',
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );
        """)

        # 6. Retrieval Logs Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS retrieval_logs (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            query TEXT NOT NULL,
            retrieved_chunk_ids TEXT NOT NULL,
            response TEXT NOT NULL,
            latency REAL NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );
        """)

        # 7. Usage Limits Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_limits (
            user_id TEXT PRIMARY KEY,
            requests_today INTEGER DEFAULT 0,
            tokens_used INTEGER DEFAULT 0,
            reset_date TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # 8. Sessions Table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        """)

        # 9. OTPs Table (helper table for OTP flow)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS otps (
            email TEXT PRIMARY KEY,
            otp_hash TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            attempts INTEGER DEFAULT 0
        );
        """)

        conn.commit()
        conn.close()

db = Database()
