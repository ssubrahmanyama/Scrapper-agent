import { useState, useRef, useEffect } from "react";

const SYSTEM_PROMPT = `You are DockerFixAgent — an expert DevOps AI that diagnoses and fixes Docker/Docker Compose deployment issues.

Your job:
1. Analyze error logs, Dockerfiles, docker-compose.yml, requirements.txt and any other files the user provides.
2. Identify ALL issues (missing packages, wrong paths, misconfigured services, entrypoint errors, volume issues, env vars, etc.)
3. For EVERY issue found, provide:
   - Clear diagnosis
   - Root cause
   - The exact fixed file content (full file, not a diff)
4. After fixes, provide a "RUN THIS" section with exact shell commands to rebuild/restart.

Known issues from the current deployment log (pre-analyzed):
- Container d6f16f2f865f (Celery worker): "exec /venv/bin/celery: no such file or directory" → venv not built correctly or celery not in requirements
- Container a7e914a6e988 (Alembic migration): "sh: 1: alembic: not found" → alembic not installed in PATH
- MariaDB: healthy but io_uring disabled (non-critical, falls back to libaio)
- Running services: Vault (8200), SearXNG (8888), MailHog (1025/8025)

Response format — always use this structure:
## 🔍 Issues Found
[numbered list of all issues]

## 🔧 Fixes

### Fix 1: [Issue Name]
**Root Cause:** ...
**File:** \`filename\`
\`\`\`dockerfile/yaml/python/bash
[complete fixed file content]
\`\`\`

### Fix 2: ...

## 🚀 Run This
\`\`\`bash
[exact commands to apply fixes and redeploy]
\`\`\`

## ✅ Verification
[commands to verify everything is working]

If the user sends just a message (not files), answer their follow-up question about the Docker issues. Be precise, technical, and thorough. Never truncate file contents.`;

const LOG_SUMMARY = `[Pre-loaded deployment log summary]
- Celery worker (d6f16f2f865f): exec /venv/bin/celery: no such file or directory (repeating)
- Migration runner (a7e914a6e988): sh: 1: alembic: not found (repeating)
- MariaDB (1af4f3107d61): healthy, running on port 3306
- Vault: up on 8200, SearXNG: up on 8888, MailHog: up on 1025/8025`;

const fileTemplates = {
  dockerfile: `# Paste your Dockerfile here`,
  compose: `# Paste your docker-compose.yml here`,
  requirements: `# Paste your requirements.txt here`,
  other: `# Paste any other config file here`,
};

function TypingDots() {
  return (
    <span style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 6,
            height: 6,
            borderRadius: "50%",
            background: "#00ff88",
            display: "inline-block",
            animation: `blink 1.2s ${i * 0.2}s infinite`,
          }}
        />
      ))}
    </span>
  );
}

function FileTab({ label, active, onClick, hasContent }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 14px",
        background: active ? "#00ff88" : "transparent",
        color: active ? "#0a0e0a" : hasContent ? "#00ff88" : "#4a5a4a",
        border: "1px solid",
        borderColor: active ? "#00ff88" : hasContent ? "#1a3a1a" : "#111",
        fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
        fontSize: 11,
        cursor: "pointer",
        borderRadius: 3,
        fontWeight: active ? 700 : 400,
        transition: "all 0.15s",
        letterSpacing: "0.05em",
      }}
    >
      {hasContent && !active && <span style={{ marginRight: 4, color: "#00ff88" }}>●</span>}
      {label}
    </button>
  );
}

function MessageBlock({ msg }) {
  const isUser = msg.role === "user";
  return (
    <div
      style={{
        marginBottom: 20,
        display: "flex",
        flexDirection: "column",
        alignItems: isUser ? "flex-end" : "flex-start",
      }}
    >
      <div
        style={{
          fontSize: 10,
          color: "#3a5a3a",
          marginBottom: 4,
          fontFamily: "monospace",
          letterSpacing: "0.08em",
        }}
      >
        {isUser ? "YOU" : "DOCKER_FIX_AGENT"}
      </div>
      <div
        style={{
          maxWidth: "92%",
          padding: "12px 16px",
          background: isUser ? "#0d1f0d" : "#080e08",
          border: `1px solid ${isUser ? "#1a3a1a" : "#0f2f0f"}`,
          borderRadius: isUser ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
          color: isUser ? "#a0c8a0" : "#c8e8c8",
          fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
          fontSize: 12.5,
          lineHeight: 1.75,
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        <FormattedContent text={msg.content} />
      </div>
    </div>
  );
}

function FormattedContent({ text }) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("```")) {
          const lines = part.split("\n");
          const lang = lines[0].replace("```", "").trim();
          const code = lines.slice(1, -1).join("\n");
          return (
            <CodeBlock key={i} lang={lang} code={code} />
          );
        }
        return <InlineFormatted key={i} text={part} />;
      })}
    </>
  );
}

function InlineFormatted({ text }) {
  const lines = text.split("\n");
  return (
    <>
      {lines.map((line, i) => {
        if (line.startsWith("## ")) {
          return (
            <div key={i} style={{ color: "#00ff88", fontWeight: 700, fontSize: 13, marginTop: 14, marginBottom: 4, letterSpacing: "0.05em" }}>
              {line.replace("## ", "")}
            </div>
          );
        }
        if (line.startsWith("### ")) {
          return (
            <div key={i} style={{ color: "#60d860", fontWeight: 700, marginTop: 10, marginBottom: 2 }}>
              {line.replace("### ", "▸ ")}
            </div>
          );
        }
        if (line.startsWith("**") && line.endsWith("**")) {
          return <div key={i} style={{ color: "#80e880", fontWeight: 700 }}>{line.replace(/\*\*/g, "")}</div>;
        }
        const boldParts = line.split(/(\*\*.*?\*\*)/g);
        return (
          <div key={i}>
            {boldParts.map((p, j) =>
              p.startsWith("**") ? (
                <strong key={j} style={{ color: "#80e880" }}>{p.replace(/\*\*/g, "")}</strong>
              ) : (
                <span key={j}>{p}</span>
              )
            )}
          </div>
        );
      })}
    </>
  );
}

function CodeBlock({ lang, code }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  const colors = {
    bash: "#ffcc44",
    dockerfile: "#44aaff",
    yaml: "#ff88aa",
    python: "#88ccff",
    default: "#aaffaa",
  };
  const accent = colors[lang] || colors.default;
  return (
    <div style={{ margin: "10px 0", borderRadius: 6, overflow: "hidden", border: `1px solid #1a2a1a` }}>
      <div style={{
        background: "#0a150a",
        padding: "5px 12px",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
      }}>
        <span style={{ color: accent, fontSize: 10, fontWeight: 700, letterSpacing: "0.1em" }}>
          {lang.toUpperCase() || "CODE"}
        </span>
        <button
          onClick={copy}
          style={{
            background: "transparent",
            border: "none",
            color: copied ? "#00ff88" : "#3a5a3a",
            fontSize: 10,
            cursor: "pointer",
            fontFamily: "monospace",
            padding: "2px 6px",
          }}
        >
          {copied ? "✓ COPIED" : "COPY"}
        </button>
      </div>
      <pre style={{
        background: "#050a05",
        margin: 0,
        padding: "12px 14px",
        overflowX: "auto",
        fontSize: 11.5,
        color: "#b8d8b8",
        lineHeight: 1.6,
      }}>
        {code}
      </pre>
    </div>
  );
}

export default function DockerFixAgent() {
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      content: `## 🐳 DockerFixAgent Online

Pre-loaded your deployment log. Two critical failures detected:

**① Celery worker** → \`/venv/bin/celery\` not found
**② Alembic migrations** → \`alembic\` not in PATH

To generate precise fixes, paste your project files in the tabs on the right, then hit **ANALYZE & FIX**.

Or ask me anything about the errors directly.`,
    },
  ]);
  const [files, setFiles] = useState({
    dockerfile: "",
    compose: "",
    requirements: "",
    other: "",
  });
  const [activeTab, setActiveTab] = useState("dockerfile");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const chatEndRef = useRef(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const buildUserMessage = (userText, includeFiles) => {
    let content = LOG_SUMMARY + "\n\n";
    if (includeFiles) {
      const fileMap = {
        "Dockerfile": files.dockerfile,
        "docker-compose.yml": files.compose,
        "requirements.txt": files.requirements,
        "Other config": files.other,
      };
      Object.entries(fileMap).forEach(([name, content_]) => {
        if (content_.trim()) {
          content += `\n--- ${name} ---\n${content_}\n`;
        }
      });
    }
    content += `\nUser message: ${userText}`;
    return content;
  };

  const callClaude = async (userContent) => {
    const history = messages
      .filter((m) => m.role !== "system")
      .map((m) => ({ role: m.role, content: m.content }));

    const response = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: "claude-sonnet-4-20250514",
        max_tokens: 1000,
        system: SYSTEM_PROMPT,
        messages: [...history, { role: "user", content: userContent }],
      }),
    });
    const data = await response.json();
    return data.content?.[0]?.text || "No response received.";
  };

  const handleAnalyze = async () => {
    const hasFiles = Object.values(files).some((f) => f.trim());
    const userMsg = hasFiles
      ? "Please analyze all the provided files along with the deployment log and fix every issue."
      : "Analyze the deployment log and provide fixes based on common Docker patterns for the errors shown.";

    const displayMsg = hasFiles
      ? "📁 Sending project files for analysis — fix all issues found."
      : "🔍 Analyze the deployment log and generate fixes.";

    setMessages((prev) => [...prev, { role: "user", content: displayMsg }]);
    setLoading(true);

    try {
      const fullMessage = buildUserMessage(userMsg, true);
      const reply = await callClaude(fullMessage);
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", content: `❌ Error: ${e.message}` }]);
    }
    setLoading(false);
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;
    const userText = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userText }]);
    setLoading(true);
    try {
      const reply = await callClaude(buildUserMessage(userText, false));
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (e) {
      setMessages((prev) => [...prev, { role: "assistant", content: `❌ Error: ${e.message}` }]);
    }
    setLoading(false);
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div style={{
      fontFamily: "'JetBrains Mono', 'Fira Mono', monospace",
      background: "#020602",
      minHeight: "100vh",
      color: "#c0e0c0",
      display: "flex",
      flexDirection: "column",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
        @keyframes blink { 0%,80%,100%{opacity:0} 40%{opacity:1} }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
        ::-webkit-scrollbar { width: 4px; height: 4px; }
        ::-webkit-scrollbar-track { background: #050a05; }
        ::-webkit-scrollbar-thumb { background: #1a3a1a; border-radius: 2px; }
        textarea:focus { outline: none; }
      `}</style>

      {/* Header */}
      <div style={{
        background: "#040904",
        borderBottom: "1px solid #0d1f0d",
        padding: "10px 20px",
        display: "flex",
        alignItems: "center",
        gap: 12,
      }}>
        <div style={{
          width: 10, height: 10, borderRadius: "50%",
          background: "#00ff88",
          animation: "pulse 2s infinite",
          boxShadow: "0 0 8px #00ff88",
        }} />
        <span style={{ color: "#00ff88", fontSize: 13, fontWeight: 700, letterSpacing: "0.1em" }}>
          DOCKER_FIX_AGENT
        </span>
        <span style={{ color: "#2a4a2a", fontSize: 11 }}>v1.0 // scrapper-agent@ip-172-31-43-197</span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          {[
            { label: "CELERY", status: "ERR" },
            { label: "ALEMBIC", status: "ERR" },
            { label: "MARIADB", status: "OK" },
            { label: "VAULT", status: "OK" },
          ].map(({ label, status }) => (
            <span key={label} style={{
              fontSize: 9,
              padding: "2px 6px",
              borderRadius: 2,
              background: status === "ERR" ? "#1a0505" : "#051a05",
              color: status === "ERR" ? "#ff4444" : "#00aa44",
              border: `1px solid ${status === "ERR" ? "#330000" : "#003300"}`,
              letterSpacing: "0.08em",
            }}>
              {label}:{status}
            </span>
          ))}
        </div>
      </div>

      {/* Body */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden", height: "calc(100vh - 48px)" }}>

        {/* Chat Panel */}
        <div style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid #0d1f0d",
          minWidth: 0,
        }}>
          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: "16px 20px" }}>
            {messages.map((msg, i) => (
              <MessageBlock key={i} msg={msg} />
            ))}
            {loading && (
              <div style={{ display: "flex", alignItems: "center", gap: 10, color: "#3a5a3a", fontSize: 11 }}>
                <TypingDots />
                <span>analyzing...</span>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Input */}
          <div style={{
            borderTop: "1px solid #0d1f0d",
            padding: "10px 16px",
            background: "#030803",
            display: "flex",
            gap: 8,
            alignItems: "flex-end",
          }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKey}
              placeholder="Ask about any error... (Enter to send)"
              rows={2}
              style={{
                flex: 1,
                background: "#080e08",
                border: "1px solid #1a2a1a",
                borderRadius: 4,
                color: "#a0c8a0",
                padding: "8px 10px",
                fontFamily: "inherit",
                fontSize: 12,
                resize: "none",
                lineHeight: 1.5,
              }}
            />
            <button
              onClick={handleSend}
              disabled={loading || !input.trim()}
              style={{
                padding: "8px 14px",
                background: loading || !input.trim() ? "#0a150a" : "#00ff88",
                color: loading || !input.trim() ? "#2a4a2a" : "#020602",
                border: "none",
                borderRadius: 4,
                fontFamily: "inherit",
                fontSize: 11,
                fontWeight: 700,
                cursor: loading || !input.trim() ? "default" : "pointer",
                letterSpacing: "0.08em",
                whiteSpace: "nowrap",
              }}
            >
              SEND ▶
            </button>
          </div>
        </div>

        {/* Files Panel */}
        <div style={{
          width: 380,
          display: "flex",
          flexDirection: "column",
          background: "#030703",
        }}>
          {/* Tab bar */}
          <div style={{
            padding: "10px 12px 0",
            borderBottom: "1px solid #0d1f0d",
            background: "#040904",
          }}>
            <div style={{ fontSize: 9, color: "#2a4a2a", letterSpacing: "0.1em", marginBottom: 8 }}>
              PROJECT FILES // paste to enable precise fixes
            </div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap", paddingBottom: 10 }}>
              {[
                { key: "dockerfile", label: "Dockerfile" },
                { key: "compose", label: "compose.yml" },
                { key: "requirements", label: "requirements.txt" },
                { key: "other", label: "+ other" },
              ].map(({ key, label }) => (
                <FileTab
                  key={key}
                  label={label}
                  active={activeTab === key}
                  onClick={() => setActiveTab(key)}
                  hasContent={!!files[key].trim()}
                />
              ))}
            </div>
          </div>

          {/* Editor */}
          <textarea
            value={files[activeTab]}
            onChange={(e) => setFiles((f) => ({ ...f, [activeTab]: e.target.value }))}
            placeholder={fileTemplates[activeTab]}
            style={{
              flex: 1,
              background: "#030703",
              border: "none",
              color: "#90c890",
              padding: "14px",
              fontFamily: "inherit",
              fontSize: 11.5,
              resize: "none",
              lineHeight: 1.7,
            }}
          />

          {/* Analyze button */}
          <div style={{ padding: "10px 12px", borderTop: "1px solid #0d1f0d", background: "#040904" }}>
            <button
              onClick={handleAnalyze}
              disabled={loading}
              style={{
                width: "100%",
                padding: "10px",
                background: loading ? "#0a150a" : "#00ff88",
                color: loading ? "#2a4a2a" : "#020602",
                border: "none",
                borderRadius: 4,
                fontFamily: "inherit",
                fontSize: 12,
                fontWeight: 700,
                cursor: loading ? "default" : "pointer",
                letterSpacing: "0.1em",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: 8,
              }}
            >
              {loading ? <><TypingDots /> ANALYZING...</> : "⚡ ANALYZE & FIX ALL ISSUES"}
            </button>
            <div style={{ fontSize: 9, color: "#2a4a2a", textAlign: "center", marginTop: 6, letterSpacing: "0.05em" }}>
              {Object.values(files).some((f) => f.trim())
                ? `${Object.values(files).filter((f) => f.trim()).length} file(s) loaded`
                : "works without files — better with them"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
