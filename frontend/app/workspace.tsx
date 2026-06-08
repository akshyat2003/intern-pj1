"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Bot, Cpu, Coins, Eye, EyeOff, FileUp, LogOut, Send, UploadCloud, UserPlus, Plus, MessageSquare } from "lucide-react";



type Source = {
  filename: string;
  chunk_id: number;
  text: string;
  score: number;
};

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: Source[] | null;
};

type ChatSession = {
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type User = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  is_verified: boolean;
  tokens_used?: number;
  token_limit?: number;
};

type AuthMode = "login" | "signup";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://127.0.0.1:8000"
    : "/api");
const TOKEN_KEY = "rag_chatbot_token";

function createMockJwt(email: string, firstName: string, lastName: string, phoneNumber: string): string {
  const header = btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = btoa(
    JSON.stringify({
      sub: `mock-uid-${email.replace(/[^a-zA-Z0-9]/g, "")}`,
      email: email,
      name: `${firstName} ${lastName}`,
      phone_number: phoneNumber,
      exp: Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60,
    })
  );
  return `${header}.${payload}.signature`;
}

async function readJson(response: Response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || "Request failed.");
  }
  return data;
}

const COUNTRY_CODES = [
  { name: "India", dial: "+91", flag: "🇮🇳", code: "IN" },
  { name: "United States", dial: "+1", flag: "🇺🇸", code: "US" },
  { name: "United Kingdom", dial: "+44", flag: "🇬🇧", code: "GB" },
  { name: "Canada", dial: "+1", flag: "🇨🇦", code: "CA" },
  { name: "Australia", dial: "+61", flag: "🇦🇺", code: "AU" },
  { name: "Singapore", dial: "+65", flag: "🇸🇬", code: "SG" },
  { name: "United Arab Emirates", dial: "+971", flag: "🇦🇪", code: "AE" },
  { name: "Bangladesh", dial: "+880", flag: "🇧🇩", code: "BD" },
  { name: "Nepal", dial: "+977", flag: "🇳🇵", code: "NP" },
  { name: "Sri Lanka", dial: "+94", flag: "🇱🇰", code: "LK" },
  { name: "Cambodia", dial: "+855", flag: "🇰🇭", code: "KH" },
  { name: "Malaysia", dial: "+60", flag: "🇲🇾", code: "MY" },
  { name: "Germany", dial: "+49", flag: "🇩🇪", code: "DE" },
  { name: "France", dial: "+33", flag: "🇫🇷", code: "FR" },
  { name: "Japan", dial: "+81", flag: "🇯🇵", code: "JP" },
  { name: "Vietnam", dial: "+84", flag: "🇻🇳", code: "VN" },
  { name: "Thailand", dial: "+66", flag: "🇹🇭", code: "TH" },
  { name: "Indonesia", dial: "+62", flag: "🇮🇩", code: "ID" },
  { name: "Philippines", dial: "+63", flag: "🇵🇭", code: "PH" },
  { name: "Pakistan", dial: "+92", flag: "🇵🇰", code: "PK" },
  { name: "Saudi Arabia", dial: "+966", flag: "🇸🇦", code: "SA" },
  { name: "South Africa", dial: "+27", flag: "🇿🇦", code: "ZA" },
  { name: "New Zealand", dial: "+64", flag: "🇳🇿", code: "NZ" },
  { name: "Ireland", dial: "+353", flag: "🇮🇪", code: "IE" },
  { name: "Netherlands", dial: "+31", flag: "🇳🇱", code: "NL" },
  { name: "Switzerland", dial: "+41", flag: "🇨🇭", code: "CH" },
  { name: "Belgium", dial: "+32", flag: "🇧🇪", code: "BE" },
  { name: "Sweden", dial: "+46", flag: "🇸🇪", code: "SE" },
  { name: "Norway", dial: "+47", flag: "🇳🇴", code: "NO" },
  { name: "Denmark", dial: "+45", flag: "🇩🇰", code: "DK" },
  { name: "Austria", dial: "+43", flag: "🇦🇹", code: "AT" },
  { name: "Spain", dial: "+34", flag: "🇪🇸", code: "ES" },
  { name: "Italy", dial: "+39", flag: "🇮🇹", code: "IT" },
  { name: "Portugal", dial: "+351", flag: "🇵🇹", code: "PT" },
];


export default function ChatWorkspace({ status }: { status: string }) {
  const [token, setToken] = useState<string>(() => {
    if (typeof window === "undefined") {
      return "";
    }
    return window.localStorage.getItem(TOKEN_KEY) || "";
  });
  const [user, setUser] = useState<User | null>(null);
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [authMessage, setAuthMessage] = useState("");
  const [authError, setAuthError] = useState("");
  const [isAuthLoading, setIsAuthLoading] = useState(false);
  const [signupForm, setSignupForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone_number: "",
    password: "",
  });
  const [loginForm, setLoginForm] = useState({ identifier: "", password: "" });

  const [showPassword, setShowPassword] = useState(false);
  const [countryCode, setCountryCode] = useState("+91");

  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>("");
  const [uploadError, setUploadError] = useState<string>("");
  const [isUploading, setIsUploading] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string>("");
  const [isAsking, setIsAsking] = useState(false);
  const [lastQueryStats, setLastQueryStats] = useState<{
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
    contextWindowLimit: number;
  } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canAsk = useMemo(() => question.trim().length > 0 && !isAsking && !!token, [question, isAsking, token]);

  useEffect(() => {
    if (!token) {
      return;
    }

    let isActive = true;

    async function loadAccount() {
      try {
        const profileResponse = await fetch(`${API_BASE_URL}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const profile = await readJson(profileResponse);
        const sessionsResponse = await fetch(`${API_BASE_URL}/chat/sessions`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const fetchedSessions = await readJson(sessionsResponse);

        let activeSessionId = currentSessionId;
        if (!activeSessionId) {
          if (fetchedSessions.length > 0) {
            activeSessionId = fetchedSessions[0].session_id;
          } else {
            activeSessionId = Math.random().toString(36).slice(2);
          }
        }

        const historyResponse = await fetch(`${API_BASE_URL}/chat/history?session_id=${activeSessionId}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const history = await readJson(historyResponse);

        if (isActive) {
          setUser(profile);
          setSessions(fetchedSessions);
          setCurrentSessionId(activeSessionId);
          setMessages(history.map((item: Message) => ({ role: item.role, content: item.content, sources: item.sources })));
        }
      } catch {
        if (isActive) {
          logout();
        }
      }
    }

    void loadAccount();

    return () => {
      isActive = false;
    };
  }, [token]);

  async function authFetch(path: string, options: RequestInit = {}, activeToken = token) {
    return fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${activeToken}`,
      },
    });
  }

  async function logout() {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    setMessages([]);
    setSessions([]);
    setCurrentSessionId("");
    setUploadStatus("");
    setUploadError("");
  }

  function createNewSession() {
    const newId = Math.random().toString(36).slice(2);
    setCurrentSessionId(newId);
    setMessages([]);
    setLastQueryStats(null);
  }

  async function loadSession(id: string) {
    setCurrentSessionId(id);
    setLastQueryStats(null);
    try {
      const response = await authFetch(`/chat/history?session_id=${id}`);
      const history = await readJson(response);
      setMessages(history.map((item: Message) => ({ role: item.role, content: item.content, sources: item.sources })));
    } catch (error) {
      console.error("Failed to load session history");
    }
  }

  async function signup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsAuthLoading(true);
    setAuthError("");
    setAuthMessage("");

    // Password complexity validation
    const password = signupForm.password;
    if (password.length < 8) {
      setAuthError("Password must be at least 8 characters long.");
      setIsAuthLoading(false);
      return;
    }
    if (!/[A-Z]/.test(password)) {
      setAuthError("Password must contain at least one uppercase letter (A–Z).");
      setIsAuthLoading(false);
      return;
    }
    if (!/[a-z]/.test(password)) {
      setAuthError("Password must contain at least one lowercase letter (a–z).");
      setIsAuthLoading(false);
      return;
    }
    if (!/[0-9]/.test(password)) {
      setAuthError("Password must contain at least one number (0–9).");
      setIsAuthLoading(false);
      return;
    }
    const specialCharSet = /[@#$%&*_\-+=!?^~.,;/\\|()[\]{}':"`<>]/;
    if (!specialCharSet.test(password)) {
      setAuthError("Password must contain at least one special character (@, #, $, %, &, *, etc.).");
      setIsAuthLoading(false);
      return;
    }

    try {
      const formattedPhone = `${countryCode}${signupForm.phone_number.replace(/\D/g, "")}`;
      const response = await fetch(`${API_BASE_URL}/auth/signup`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          first_name: signupForm.first_name,
          last_name: signupForm.last_name,
          email: signupForm.email,
          phone_number: formattedPhone,
          password: signupForm.password,
        }),
      });

      const data = await readJson(response);
      setAuthMessage(data.message);
      setAuthMode("login");
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Signup failed.");
    } finally {
      setIsAuthLoading(false);
    }
  }



  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsAuthLoading(true);
    setAuthError("");
    setAuthMessage("");
    try {
      const response = await fetch(`${API_BASE_URL}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(loginForm),
      });



      const data = await readJson(response);
      window.localStorage.setItem(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setUser(data.user);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setIsAuthLoading(false);
    }
  }

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
      const response = await authFetch("/upload", {
        method: "POST",
        body: formData,
      });
      const data = await readJson(response);
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
      const response = await authFetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: trimmed, session_id: currentSessionId }),
      });
      const data = await readJson(response);
      setMessages((current) => [...current, { role: "assistant", content: data.answer, sources: data.sources }]);

      if (data.prompt_tokens !== undefined) {
        setLastQueryStats({
          promptTokens: data.prompt_tokens,
          completionTokens: data.completion_tokens,
          totalTokens: data.total_tokens,
          contextWindowLimit: data.context_window_limit,
        });
      }
      if (data.tokens_used !== undefined && user) {
        setUser((prev) => prev ? {
          ...prev,
          tokens_used: data.tokens_used,
          token_limit: data.token_limit,
        } : null);
      }

      // If this was the first message in the session, reload the sessions list to update the title
      if (messages.length === 0) {
        authFetch("/chat/sessions")
          .then(readJson)
          .then(fetchedSessions => setSessions(fetchedSessions))
          .catch(console.error);
      }
    } catch (error) {
      const content = error instanceof Error ? error.message : "Chat request failed.";
      setMessages((current) => [...current, { role: "assistant", content }]);
    } finally {
      setIsAsking(false);
    }
  }

  if (!token || !user) {
    return (
      <>
        <header className="topbar">
          <div className="topbar-inner">
            <div className="brand">
              <span className="brand-mark" aria-hidden="true">
                <Bot size={20} />
              </span>
              <span>RAG Chatbot</span>
            </div>
          </div>
        </header>
        <section className="auth-shell">
          <div className="panel auth-panel">
            <div className="auth-heading">
              <UserPlus size={24} />
              <div>
                <h1>{authMode === "signup" ? "Create account" : "Sign in"}</h1>
                <p>Use your account to keep documents and chat history saved.</p>
              </div>
            </div>

            {authMode === "login" || authMode === "signup" ? (
              <div className="auth-tabs" aria-label="Authentication options">
                <button type="button" className={authMode === "login" ? "active" : ""} onClick={() => { setAuthMode("login"); setShowPassword(false); setAuthError(""); setAuthMessage(""); }}>
                  Login
                </button>
                <button type="button" className={authMode === "signup" ? "active" : ""} onClick={() => { setAuthMode("signup"); setShowPassword(false); setAuthError(""); setAuthMessage(""); }}>
                  Sign up
                </button>
              </div>
            ) : null}

            {authMode === "signup" ? (
              <form className="auth-form" onSubmit={signup}>
                <input placeholder="First name" value={signupForm.first_name} onChange={(event) => setSignupForm({ ...signupForm, first_name: event.target.value })} />
                <input placeholder="Last name" value={signupForm.last_name} onChange={(event) => setSignupForm({ ...signupForm, last_name: event.target.value })} />
                <input placeholder="Email" type="email" value={signupForm.email} onChange={(event) => setSignupForm({ ...signupForm, email: event.target.value })} />
                <div className="phone-container">
                  <select
                    className="country-select"
                    value={countryCode}
                    onChange={(event) => setCountryCode(event.target.value)}
                    aria-label="Country Code"
                  >
                    {COUNTRY_CODES.map((c) => (
                      <option key={`${c.code}-${c.dial}`} value={c.dial}>
                        {c.flag} {c.dial} ({c.name})
                      </option>
                    ))}
                  </select>
                  <input
                    placeholder="Phone number"
                    value={signupForm.phone_number}
                    onChange={(event) => setSignupForm({ ...signupForm, phone_number: event.target.value })}
                  />
                </div>
                <div className="password-container">
                  <input
                    placeholder="Password"
                    type={showPassword ? "text" : "password"}
                    value={signupForm.password}
                    onChange={(event) => setSignupForm({ ...signupForm, password: event.target.value })}
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                <div style={{ fontSize: "11px", color: "var(--fg-muted, #6b7280)", marginTop: "-6px", marginBottom: "12px", textAlign: "left", lineHeight: "1.4" }}>
                  Password requirements: At least 8 characters, including A–Z, a–z, 0–9, and a special character (@, #, $, %, etc.).
                </div>
                <button className="primary-button" type="submit" disabled={isAuthLoading}>{isAuthLoading ? "Creating" : "Create account"}</button>
              </form>
            ) : null}





            {authMode === "login" ? (
              <form className="auth-form" onSubmit={login}>
                <input placeholder="Email or Phone number" type="text" value={loginForm.identifier} onChange={(event) => setLoginForm({ ...loginForm, identifier: event.target.value })} />
                <div className="password-container">
                  <input
                    placeholder="Password"
                    type={showPassword ? "text" : "password"}
                    value={loginForm.password}
                    onChange={(event) => setLoginForm({ ...loginForm, password: event.target.value })}
                  />
                  <button
                    type="button"
                    className="password-toggle"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
                <button className="primary-button" type="submit" disabled={isAuthLoading}>{isAuthLoading ? "Signing in" : "Login"}</button>
              </form>
            ) : null}

            {authMessage ? <div className="message">{authMessage}</div> : null}
            {authError ? <div className="message error">{authError}</div> : null}
          </div>
        </section>
      </>
    );
  }

  return (
    <>
      <header className="topbar">
        <div className="topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">
              <Bot size={20} />
            </span>
            <span>RAG Chatbot</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <div className="status-pill">{status}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', borderLeft: '1px solid var(--line)', paddingLeft: '16px' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', lineHeight: '1.2' }}>
                <strong style={{ fontSize: '14px', fontWeight: 600 }}>{user.first_name} {user.last_name}</strong>
                <span style={{ fontSize: '12px', color: 'var(--muted)' }}>{user.email || user.phone_number}</span>
              </div>
              <button className="icon-button" type="button" onClick={logout} title="Logout" style={{ width: '38px', height: '38px' }}>
                <LogOut size={18} />
              </button>
            </div>
          </div>
        </div>
      </header>
      <section className="workspace">
        <aside className="panel upload-panel">
          
          <div className="chat-history-section" style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 className="panel-heading" style={{ fontSize: '16px', margin: 0, display: 'flex', alignItems: 'center', gap: '8px' }}>
                <MessageSquare size={16} /> Chat History
              </h2>
              <button className="secondary-button" style={{ minHeight: '32px', padding: '0 12px', fontSize: '13px' }} onClick={createNewSession}>
                <Plus size={14} /> New
              </button>
            </div>
            <div className="history-list" style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '250px', overflowY: 'auto', paddingRight: '4px' }}>
              {sessions.map(s => (
                <button
                  key={s.session_id}
                  onClick={() => loadSession(s.session_id)}
                  style={{
                    textAlign: 'left',
                    padding: '10px 12px',
                    borderRadius: '8px',
                    border: '1px solid',
                    borderColor: currentSessionId === s.session_id ? 'var(--accent)' : 'transparent',
                    background: currentSessionId === s.session_id ? 'rgba(59, 130, 246, 0.08)' : 'rgba(241, 245, 249, 0.5)',
                    color: currentSessionId === s.session_id ? 'var(--accent-dark)' : 'var(--foreground)',
                    cursor: 'pointer',
                    fontSize: '13px',
                    fontWeight: currentSessionId === s.session_id ? 600 : 400,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    transition: 'all 0.2s ease'
                  }}
                >
                  {s.title}
                </button>
              ))}
              {sessions.length === 0 && (
                <div style={{ fontSize: '13px', color: 'var(--muted)', textAlign: 'center', padding: '12px', background: 'rgba(241, 245, 249, 0.5)', borderRadius: '8px' }}>
                  No previous chats
                </div>
              )}
            </div>
          </div>

          {/* Token Quota Panel */}
          <div className="stats-section" style={{ marginTop: 0 }}>
            <h2 className="stats-section-title">
              <Coins size={16} /> Tokens Used
            </h2>

            {/* User Token Quota */}
            <div className="stats-card">
              <div className="stats-label-row">
                <span className="stats-title">Token Quota</span>
                <span className="stats-values">
                  {(user.tokens_used ?? 0).toLocaleString()} / {(user.token_limit ?? 50000).toLocaleString()}
                </span>
              </div>

              {(() => {
                const used = user.tokens_used ?? 0;
                const limit = user.token_limit ?? 50000;
                const ratio = Math.min(100, (used / limit) * 100);
                const leftoverPercent = Math.max(0, 100 - ratio).toFixed(1);
                let statusClass = "safe";
                if (ratio > 85) statusClass = "critical";
                else if (ratio > 60) statusClass = "warning";

                return (
                  <>
                    <div className="progress-track" title={`${ratio.toFixed(1)}% used`}>
                      <div
                        className={`progress-fill ${statusClass}`}
                        style={{ width: `${ratio}%` }}
                      />
                    </div>
                    <div className="stats-footer">
                      <span>{ratio.toFixed(1)}% used</span>
                      <span className={`percentage-left ${statusClass}`}>{leftoverPercent}% left</span>
                    </div>
                  </>
                );
              })()}
            </div>

            {/* Context Window Stats */}
            {lastQueryStats && (
              <div className="stats-card" style={{ borderTop: "1px solid rgba(15, 118, 110, 0.1)", paddingTop: "12px" }}>
                <div className="stats-label-row">
                  <span className="stats-title" style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <Cpu size={14} /> Context Window
                  </span>
                  <span className="stats-values">
                    {lastQueryStats.totalTokens.toLocaleString()} / {lastQueryStats.contextWindowLimit.toLocaleString()}
                  </span>
                </div>

                {(() => {
                  const used = lastQueryStats.totalTokens;
                  const limit = lastQueryStats.contextWindowLimit;
                  const ratio = Math.min(100, (used / limit) * 100);
                  const leftoverPercent = Math.max(0, 100 - ratio).toFixed(1);
                  let statusClass = "safe";
                  if (ratio > 85) statusClass = "critical";
                  else if (ratio > 60) statusClass = "warning";

                  return (
                    <>
                      <div className="progress-track" title={`${ratio.toFixed(1)}% used`}>
                        <div
                          className={`progress-fill ${statusClass}`}
                          style={{ width: `${ratio}%` }}
                        />
                      </div>
                      <div className="stats-footer">
                        <span>{ratio.toFixed(1)}% used</span>
                        <span className={`percentage-left ${statusClass}`}>{leftoverPercent}% left</span>
                      </div>
                      <div className="context-breakdown">
                        <div className="context-breakdown-item">
                          <span className="context-breakdown-label">Prompt</span>
                          <span className="context-breakdown-value">{lastQueryStats.promptTokens.toLocaleString()} tkn</span>
                        </div>
                        <div className="context-breakdown-item">
                          <span className="context-breakdown-label">Response</span>
                          <span className="context-breakdown-value">{lastQueryStats.completionTokens.toLocaleString()} tkn</span>
                        </div>
                      </div>
                    </>
                  );
                })()}
              </div>
            )}
          </div>

          <h1 className="panel-heading">Upload knowledge</h1>
          <p className="panel-copy">Documents and chat history are saved to your account.</p>
          <div className="drop-zone">
            <UploadCloud size={34} />
            <input
              ref={fileInputRef}
              className="file-input"
              type="file"
              accept=".txt,.md,.pdf,.docx,.csv,.ppt,.pptx"
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
              <p className="chat-subtitle">Answers use your saved documents. History reloads after login.</p>
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
              placeholder="Ask something about your uploaded files"
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
    </>
  );
}
