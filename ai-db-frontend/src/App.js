import { useState, useRef, useEffect } from "react";

const API = "http://localhost:8000";

// ── Palette ──────────────────────────────────────────────────────────────────
const theme = {
  bg: "#0a0a0f",
  surface: "#11111a",
  card: "#16161f",
  border: "#1e1e2e",
  accent: "#6ee7f7",
  accent2: "#a78bfa",
  accent3: "#34d399",
  warn: "#f59e0b",
  text: "#e2e8f0",
  muted: "#64748b",
  danger: "#f87171",
};

// ── Tiny helpers ─────────────────────────────────────────────────────────────
const badge = (label, color) => (
  <span
    style={{
      background: color + "22",
      color,
      border: `1px solid ${color}44`,
      borderRadius: 6,
      padding: "2px 10px",
      fontSize: 11,
      fontWeight: 700,
      letterSpacing: 1,
      textTransform: "uppercase",
    }}
  >
    {label}
  </span>
);

const queryColor = { SQL: theme.accent3, VECTOR: theme.accent2, HYBRID: theme.warn };

// ── Animated dots ─────────────────────────────────────────────────────────────
function Dots() {
  return (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: theme.accent,
            animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </span>
  );
}

// ── Nav Tab ───────────────────────────────────────────────────────────────────
function Tab({ label, icon, active, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? theme.accent + "18" : "transparent",
        color: active ? theme.accent : theme.muted,
        border: "none",
        borderBottom: active ? `2px solid ${theme.accent}` : "2px solid transparent",
        padding: "12px 24px",
        cursor: "pointer",
        fontFamily: "inherit",
        fontSize: 13,
        fontWeight: 600,
        letterSpacing: 0.5,
        display: "flex",
        alignItems: "center",
        gap: 8,
        transition: "all 0.2s",
      }}
    >
      <span style={{ fontSize: 16 }}>{icon}</span>
      {label}
    </button>
  );
}

// ── Upload Page ───────────────────────────────────────────────────────────────
function UploadPage() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef();

  const handleFile = (f) => {
    if (f) setFile(f);
  };

  const upload = async () => {
    if (!file) return;
    setLoading(true);
    setResult(null);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await fetch(`${API}/upload`, { method: "POST", body: fd });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      setResult({ error: e.message });
    }
    setLoading(false);
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "32px 16px" }}>
      <h2 style={{ color: theme.text, fontFamily: "inherit", fontWeight: 700, marginBottom: 6 }}>
        Upload Document
      </h2>
      <p style={{ color: theme.muted, fontSize: 13, marginBottom: 28 }}>
        PDF, TXT, PNG, JPG — AI will extract text, generate schema, and store embeddings.
      </p>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); handleFile(e.dataTransfer.files[0]); }}
        onClick={() => inputRef.current.click()}
        style={{
          border: `2px dashed ${drag ? theme.accent : theme.border}`,
          borderRadius: 16,
          padding: "48px 32px",
          textAlign: "center",
          cursor: "pointer",
          background: drag ? theme.accent + "08" : theme.card,
          transition: "all 0.2s",
          marginBottom: 20,
        }}
      >
        <div style={{ fontSize: 40, marginBottom: 12 }}>📄</div>
        <div style={{ color: theme.text, fontWeight: 600, marginBottom: 4 }}>
          {file ? file.name : "Drop file here or click to browse"}
        </div>
        <div style={{ color: theme.muted, fontSize: 12 }}>
          {file ? `${(file.size / 1024).toFixed(1)} KB` : "PDF · TXT · PNG · JPG"}
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.txt,.png,.jpg,.jpeg"
          style={{ display: "none" }}
          onChange={(e) => handleFile(e.target.files[0])}
        />
      </div>

      <button
        onClick={upload}
        disabled={!file || loading}
        style={{
          background: file && !loading ? theme.accent : theme.border,
          color: file && !loading ? "#0a0a0f" : theme.muted,
          border: "none",
          borderRadius: 10,
          padding: "12px 32px",
          fontFamily: "inherit",
          fontWeight: 700,
          fontSize: 14,
          cursor: file && !loading ? "pointer" : "not-allowed",
          transition: "all 0.2s",
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}
      >
        {loading ? <><Dots /> Processing…</> : "⚡ Upload & Process"}
      </button>

      {/* Result */}
      {result && (
        <div
          style={{
            marginTop: 28,
            background: theme.card,
            border: `1px solid ${result.error ? theme.danger + "44" : theme.accent + "44"}`,
            borderRadius: 14,
            padding: 24,
          }}
        >
          {result.error ? (
            <p style={{ color: theme.danger, margin: 0 }}>❌ {result.error}</p>
          ) : (
            <>
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
                <span style={{ fontSize: 20 }}>✅</span>
                <span style={{ color: theme.accent3, fontWeight: 700 }}>{result.message}</span>
                {badge(`${result.chunks_created} chunks`, theme.accent)}
              </div>

              {result.ai_schema?.status === "success" || result.ai_schema?.status === "partial" ? (
                <div style={{ marginBottom: 16 }}>
                  <div style={{ color: theme.muted, fontSize: 11, fontWeight: 700, letterSpacing: 1, marginBottom: 8 }}>
                    AI-GENERATED SCHEMA
                  </div>
                  <div style={{ background: theme.surface, borderRadius: 10, padding: 14, fontFamily: "monospace", fontSize: 12 }}>
                    <span style={{ color: theme.accent2 }}>CREATE TABLE</span>{" "}
                    <span style={{ color: theme.accent }}>{result.ai_schema.table}</span> {"("}
                    <br />
                    {result.ai_schema.fields.map((f, i) => (
                      <div key={i} style={{ paddingLeft: 20, color: theme.text }}>
                        <span style={{ color: theme.accent3 }}>{f.field_name}</span>{" "}
                        <span style={{ color: theme.warn }}>{f.data_type}</span>
                        {i < result.ai_schema.fields.length - 1 ? "," : ""}
                      </div>
                    ))}
                    {")"}
                  </div>
                  {/* FIX: surfaces insert_error in the UI so failures are visible,
                      not just hidden in the backend terminal logs. */}
                  {result.ai_schema.insert_error && (
                    <p style={{ color: theme.warn, fontSize: 12, marginTop: 10 }}>
                      ⚠️ {result.ai_schema.insert_error}
                    </p>
                  )}
                </div>
              ) : null}

              <div>
                <div style={{ color: theme.muted, fontSize: 11, fontWeight: 700, letterSpacing: 1, marginBottom: 6 }}>
                  TEXT PREVIEW
                </div>
                <p style={{ color: theme.muted, fontSize: 12, fontFamily: "monospace", margin: 0, lineHeight: 1.7 }}>
                  {result.preview}
                </p>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

// ── Chat Page ─────────────────────────────────────────────────────────────────
function ChatPage() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hello! Ask me anything about your uploaded documents. I'll decide whether to use SQL, vector search, or both.",
      queryType: null,
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef();

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const send = async () => {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setLoading(true);

    try {
      const res = await fetch(`${API}/ask?question=${encodeURIComponent(q)}`, { method: "POST" });
      const data = await res.json();
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          text: data.answer || data.error,
          queryType: data.query_type,
          contextPreview: data.context_preview,
        },
      ]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", text: `Error: ${e.message}`, queryType: null }]);
    }
    setLoading(false);
  };

  return (
    <div style={{ maxWidth: 720, margin: "0 auto", padding: "32px 16px", display: "flex", flexDirection: "column", height: "calc(100vh - 140px)" }}>
      <h2 style={{ color: theme.text, fontWeight: 700, marginBottom: 6 }}>Query Agent</h2>
      <p style={{ color: theme.muted, fontSize: 13, marginBottom: 20 }}>
        The AI agent automatically routes your query — SQL, vector search, or hybrid.
      </p>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14, paddingRight: 4 }}>
        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                maxWidth: "80%",
                background: msg.role === "user" ? theme.accent + "22" : theme.card,
                border: `1px solid ${msg.role === "user" ? theme.accent + "44" : theme.border}`,
                borderRadius: msg.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
                padding: "12px 16px",
              }}
            >
              {msg.queryType && (
                <div style={{ marginBottom: 8 }}>
                  {badge(`Agent: ${msg.queryType}`, queryColor[msg.queryType] || theme.muted)}
                </div>
              )}
              <p style={{ color: theme.text, margin: 0, fontSize: 14, lineHeight: 1.7, whiteSpace: "pre-wrap" }}>
                {msg.text}
              </p>
            </div>
          </div>
        ))}

        {loading && (
          <div style={{ display: "flex" }}>
            <div style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: "18px 18px 18px 4px", padding: "12px 20px" }}>
              <Dots />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask anything about your documents…"
          style={{
            flex: 1,
            background: theme.card,
            border: `1px solid ${theme.border}`,
            borderRadius: 12,
            padding: "12px 16px",
            color: theme.text,
            fontFamily: "inherit",
            fontSize: 14,
            outline: "none",
          }}
        />
        <button
          onClick={send}
          disabled={!input.trim() || loading}
          style={{
            background: input.trim() && !loading ? theme.accent : theme.border,
            color: input.trim() && !loading ? "#0a0a0f" : theme.muted,
            border: "none",
            borderRadius: 12,
            padding: "12px 22px",
            fontFamily: "inherit",
            fontWeight: 700,
            cursor: input.trim() && !loading ? "pointer" : "not-allowed",
            fontSize: 18,
          }}
        >
          ➤
        </button>
      </div>
    </div>
  );
}

// ── Schema Page ───────────────────────────────────────────────────────────────
function SchemaPage() {
  const [tables, setTables] = useState(null);
  const [selected, setSelected] = useState(null);
  const [rows, setRows] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API}/tables`)
      .then((r) => r.json())
      .then((d) => setTables(d.tables || {}))
      .catch(() => setTables({}));
  }, []);

  const loadTable = async (name) => {
    setSelected(name);
    setRows(null);
    setLoading(true);
    const res = await fetch(`${API}/table/${name}`);
    const data = await res.json();
    setRows(data.rows || []);
    setLoading(false);
  };

  return (
    <div style={{ maxWidth: 960, margin: "0 auto", padding: "32px 16px" }}>
      <h2 style={{ color: theme.text, fontWeight: 700, marginBottom: 6 }}>AI-Generated Schemas</h2>
      <p style={{ color: theme.muted, fontSize: 13, marginBottom: 28 }}>
        Tables automatically created by AI from your uploaded documents.
      </p>

      {!tables ? (
        <p style={{ color: theme.muted }}>Loading…</p>
      ) : Object.keys(tables).length === 0 ? (
        <div style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 14, padding: 32, textAlign: "center" }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>📭</div>
          <p style={{ color: theme.muted }}>No AI-generated tables yet. Upload a document first.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: 20 }}>
          {/* Table list */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {Object.entries(tables).map(([name, info]) => (
              <button
                key={name}
                onClick={() => loadTable(name)}
                style={{
                  background: selected === name ? theme.accent + "18" : theme.card,
                  border: `1px solid ${selected === name ? theme.accent + "66" : theme.border}`,
                  borderRadius: 10,
                  padding: "12px 14px",
                  textAlign: "left",
                  cursor: "pointer",
                  color: selected === name ? theme.accent : theme.text,
                  fontFamily: "inherit",
                  fontWeight: 600,
                  fontSize: 13,
                }}
              >
                🗄 {name}
                <div style={{ color: theme.muted, fontSize: 11, marginTop: 2 }}>
                  {info.row_count} rows · {info.columns.length} cols
                </div>
              </button>
            ))}
          </div>

          {/* Table content */}
          <div>
            {!selected && (
              <div style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 14, padding: 32, textAlign: "center" }}>
                <p style={{ color: theme.muted }}>← Select a table to inspect</p>
              </div>
            )}
            {selected && (
              <div style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 14, overflow: "hidden" }}>
                <div style={{ padding: "14px 20px", borderBottom: `1px solid ${theme.border}`, display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ color: theme.accent, fontWeight: 700 }}>{selected}</span>
                  {tables[selected] && badge(`${tables[selected].columns.length} columns`, theme.accent2)}
                </div>

                {loading ? (
                  <div style={{ padding: 32, textAlign: "center" }}><Dots /></div>
                ) : rows && rows.length > 0 ? (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                      <thead>
                        <tr style={{ background: theme.surface }}>
                          {Object.keys(rows[0]).map((col) => (
                            <th key={col} style={{ padding: "10px 14px", textAlign: "left", color: theme.muted, fontWeight: 700, letterSpacing: 0.5, borderBottom: `1px solid ${theme.border}`, whiteSpace: "nowrap" }}>
                              {col.toUpperCase()}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, i) => (
                          <tr key={i} style={{ borderBottom: `1px solid ${theme.border}` }}>
                            {Object.values(row).map((val, j) => (
                              <td key={j} style={{ padding: "10px 14px", color: theme.text, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {String(val ?? "—")}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p style={{ padding: 24, color: theme.muted, textAlign: "center" }}>No rows found.</p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── App Shell ─────────────────────────────────────────────────────────────────
export default function App() {
  const [tab, setTab] = useState("upload");

  return (
    <div style={{ minHeight: "100vh", background: theme.bg, fontFamily: "'IBM Plex Mono', 'Courier New', monospace", color: theme.text }}>
      {/* Global styles */}
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600;700&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 6px; height: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #1e1e2e; border-radius: 3px; }
        @keyframes pulse {
          0%, 100% { opacity: 0.3; transform: scale(0.8); }
          50% { opacity: 1; transform: scale(1.2); }
        }
        input::placeholder { color: #64748b; }
      `}</style>

      {/* Header */}
      <div style={{ background: theme.surface, borderBottom: `1px solid ${theme.border}`, padding: "0 24px" }}>
        <div style={{ maxWidth: 960, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ padding: "16px 0", display: "flex", alignItems: "center", gap: 12 }}>
            <span style={{ fontSize: 22 }}>🧠</span>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15, color: theme.accent, letterSpacing: 0.5 }}>
                AI-DB-SQL Engine
              </div>
              <div style={{ fontSize: 10, color: theme.muted, letterSpacing: 1 }}>
                AGENTIC RAG · MICROSERVICE ARCHITECTURE
              </div>
            </div>
          </div>
          <div style={{ display: "flex", gap: 2 }}>
            <Tab label="Upload" icon="📤" active={tab === "upload"} onClick={() => setTab("upload")} />
            <Tab label="Query Agent" icon="🤖" active={tab === "chat"} onClick={() => setTab("chat")} />
            <Tab label="Schemas" icon="🗄" active={tab === "schema"} onClick={() => setTab("schema")} />
          </div>
        </div>
      </div>

      {/* Page */}
      {/* FIX: previously used conditional rendering ({tab === "upload" && <UploadPage />}),
          which unmounts a page completely when you switch tabs — destroying its
          local state (uploaded file, result, chat messages, etc). Now all three
          pages stay mounted permanently, and we just show/hide them with CSS.
          This preserves state when switching tabs. */}
      <div style={{ display: tab === "upload" ? "block" : "none" }}>
        <UploadPage />
      </div>
      <div style={{ display: tab === "chat" ? "block" : "none" }}>
        <ChatPage />
      </div>
      <div style={{ display: tab === "schema" ? "block" : "none" }}>
        <SchemaPage />
      </div>
    </div>
  );
}