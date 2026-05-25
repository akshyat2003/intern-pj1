"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { Eye, EyeOff, FileUp, LogOut, Send, UploadCloud, UserPlus } from "lucide-react";

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

type User = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone_number: string;
  is_verified: boolean;
};

type AuthMode = "login" | "signup" | "verify";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  (typeof window !== "undefined" && (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1")
    ? "http://127.0.0.1:8000"
    : "/api");
const TOKEN_KEY = "rag_chatbot_token";

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


export default function ChatWorkspace() {
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
  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [verifyForm, setVerifyForm] = useState({ email: "", otp: "" });
  const [showPassword, setShowPassword] = useState(false);
  const [countryCode, setCountryCode] = useState("+91");

  const [file, setFile] = useState<File | null>(null);
  const [uploadStatus, setUploadStatus] = useState<string>("");
  const [uploadError, setUploadError] = useState<string>("");
  const [isUploading, setIsUploading] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [isAsking, setIsAsking] = useState(false);
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
        const historyResponse = await fetch(`${API_BASE_URL}/chat/history`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        const history = await readJson(historyResponse);

        if (isActive) {
          setUser(profile);
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

  function logout() {
    window.localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setUser(null);
    setMessages([]);
    setUploadStatus("");
    setUploadError("");
  }

  async function signup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsAuthLoading(true);
    setAuthError("");
    setAuthMessage("");

    try {
      const formattedPhone = `${countryCode}${signupForm.phone_number.replace(/\D/g, "")}`;
      const data = await readJson(
        await fetch(`${API_BASE_URL}/auth/signup`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            ...signupForm,
            phone_number: formattedPhone,
          }),
        }),
      );
      setVerifyForm({ email: signupForm.email, otp: data.dev_otp || "" });
      setAuthMode("verify");
      setAuthMessage(data.dev_otp ? `Use this local OTP: ${data.dev_otp}` : data.message);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "Signup failed.");
    } finally {
      setIsAuthLoading(false);
    }
  }

  async function verifyOtp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsAuthLoading(true);
    setAuthError("");
    setAuthMessage("");

    try {
      const data = await readJson(
        await fetch(`${API_BASE_URL}/auth/verify-otp`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(verifyForm),
        }),
      );
      setLoginForm({ email: verifyForm.email, password: "" });
      setAuthMode("login");
      setAuthMessage(data.message);
    } catch (error) {
      setAuthError(error instanceof Error ? error.message : "OTP verification failed.");
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
      const data = await readJson(
        await fetch(`${API_BASE_URL}/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(loginForm),
        }),
      );
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
        body: JSON.stringify({ question: trimmed }),
      });
      const data = await readJson(response);
      setMessages((current) => [...current, { role: "assistant", content: data.answer, sources: data.sources }]);
    } catch (error) {
      const content = error instanceof Error ? error.message : "Chat request failed.";
      setMessages((current) => [...current, { role: "assistant", content }]);
    } finally {
      setIsAsking(false);
    }
  }

  if (!token || !user) {
    return (
      <section className="auth-shell">
        <div className="panel auth-panel">
          <div className="auth-heading">
            <UserPlus size={24} />
            <div>
              <h1>{authMode === "signup" ? "Create account" : authMode === "verify" ? "Verify email" : "Sign in"}</h1>
              <p>Use your account to keep documents and chat history saved.</p>
            </div>
          </div>

          {authMode === "login" || authMode === "signup" ? (
            <div className="auth-tabs" aria-label="Authentication options">
              <button type="button" className={authMode === "login" ? "active" : ""} onClick={() => { setAuthMode("login"); setShowPassword(false); }}>
                Login
              </button>
              <button type="button" className={authMode === "signup" ? "active" : ""} onClick={() => { setAuthMode("signup"); setShowPassword(false); }}>
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
              <button className="primary-button" type="submit" disabled={isAuthLoading}>{isAuthLoading ? "Creating" : "Create account"}</button>
            </form>
          ) : null}

          {authMode === "verify" ? (
            <form className="auth-form" onSubmit={verifyOtp}>
              <p className="verify-copy">Enter the OTP sent to your phone/email to activate your account.</p>
              <input placeholder="Email" type="email" value={verifyForm.email} onChange={(event) => setVerifyForm({ ...verifyForm, email: event.target.value })} />
              <input placeholder="OTP" value={verifyForm.otp} onChange={(event) => setVerifyForm({ ...verifyForm, otp: event.target.value })} />
              <button className="primary-button" type="submit" disabled={isAuthLoading}>{isAuthLoading ? "Verifying" : "Verify OTP"}</button>
              <button className="secondary-button" type="button" onClick={() => setAuthMode("signup")}>Back to signup</button>
            </form>
          ) : null}

          {authMode === "login" ? (
            <form className="auth-form" onSubmit={login}>
              <input placeholder="Email" type="email" value={loginForm.email} onChange={(event) => setLoginForm({ ...loginForm, email: event.target.value })} />
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
    );
  }

  return (
    <section className="workspace">
      <aside className="panel upload-panel">
        <div className="account-strip">
          <div>
            <strong>{user.first_name} {user.last_name}</strong>
            <span>{user.email}</span>
          </div>
          <button className="icon-button" type="button" onClick={logout} title="Logout">
            <LogOut size={18} />
          </button>
        </div>
        <h1 className="panel-heading">Upload knowledge</h1>
        <p className="panel-copy">Documents and chat history are saved to your account.</p>
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
  );
}
