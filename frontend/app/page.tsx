import { Bot } from "lucide-react";
import ChatWorkspace from "./workspace";

async function getBackendStatus() {
  const baseUrl = process.env.INTERNAL_API_BASE_URL || "http://127.0.0.1:8000";
  try {
    const response = await fetch(`${baseUrl}/health`, { cache: "no-store" });
    if (!response.ok) {
      return "Backend unavailable";
    }
    const data = (await response.json()) as { chunks: number };
    return `${data.chunks} chunks indexed`;
  } catch {
    return "Backend unavailable";
  }
}

export default async function Home() {
  const status = await getBackendStatus();

  return (
    <main className="page-shell">
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              <Bot size={20} />
            </span>
            <span>RAG Chatbot</span>
          </div>
          <div className="status-pill">{status}</div>
        </div>
      </header>
      <ChatWorkspace />
    </main>
  );
}
