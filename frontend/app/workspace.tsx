"use client";

import { FormEvent, useMemo, useRef, useState } from "react";
import { FileUp, Send, UploadCloud } from "lucide-react";

type Source = {
  filename: string;
  chunk_id: number;
  text: string;
  score: number;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export default function ChatWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>("");
  const [uploadError, setUploadError] = useState<string>("");
  const [isUploading, setIsUploading] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isAsking, setIsAsking] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canAsk = useMemo(() => question.trim().length > 0 && !isAsking, [question, isAsking]);

  async function uploadFile() {
    if (!file) {
      setUploadError("Choose a file before uploading.");
      return;
    }

    setIsUploading(true);
    setUploadError("");
    setUploadStatus("");

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE_URL}/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Upload failed.");
      }
      setUploadStatus(`${data.filename} indexed with ${data.chunks_added} chunks.`);
      setFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function askQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = question.trim();
    if (!trimmed) {
      return;
    }

    setQuestion("");
    setIsAsking(true);
    setMessages((current) => [...current, { role: "user", content: trimmed }]);

    try {
      const response = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Chat request failed.");
      }
      setMessages((current) => [
        ...current,
        { role: "assistant", content: data.answer, sources: data.sources },
      ]);
    } catch (error) {
      const content = error instanceof Error ? error.message : "Chat request failed.";
      setMessages((current) => [...current, { role: "assistant", content }]);
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <section className="workspace">
      <aside className="panel upload-panel">
        <h1 className="panel-heading">Upload knowledge</h1>
        <p className="panel-copy">Add a document, then ask questions grounded in the uploaded content.</p>
        <div className="drop-zone">
          <UploadCloud size={34} />
          <input
            ref={fileInputRef}
            className="file-input"
            type="file"
            accept=".txt,.md,.pdf,.docx,.csv"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
          />
          <button className="secondary-button" type="button" onClick={uploadFile} disabled={isUploading}>
            <FileUp size={18} />
            {isUploading ? "Uploading" : "Index file"}
          </button>
        </div>
        {uploadStatus ? <div className="message">{uploadStatus}</div> : null}
        {uploadError ? <div className="message error">{uploadError}</div> : null}
      </aside>

      <section className="panel chat-panel" aria-label="Document chat">
        <div className="chat-header">
          <div>
            <h2 className="chat-title">Document Q&A</h2>
            <p className="chat-subtitle">Answers are generated from retrieved chunks.</p>
          </div>
        </div>

        <div className="message-list">
          {messages.length === 0 ? (
            <div className="empty-state">Upload a file and ask your first question.</div>
          ) : (
            messages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`bubble ${message.role}`}>
                <div>{message.content}</div>
                {message.sources?.length ? (
                  <div className="sources">
                    {message.sources.map((source) => (
                      <div className="source" key={`${source.filename}-${source.chunk_id}`}>
                        {source.filename}, chunk {source.chunk_id}: {source.text.slice(0, 220)}
                        {source.text.length > 220 ? "..." : ""}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))
          )}
          {isAsking ? <div className="bubble assistant">Thinking...</div> : null}
        </div>

        <form className="composer" onSubmit={askQuestion}>
          <textarea
            placeholder="Ask something about the uploaded file"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
          <button className="primary-button" type="submit" disabled={!canAsk}>
            <Send size={18} />
            Ask
          </button>
        </form>
      </section>
    </section>
  );
}
