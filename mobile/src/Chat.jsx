import React, { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import rehypeSanitize from "rehype-sanitize";
import { streamChat, AuthError } from "./api";
import { stripThink, rewriteRelativeImages } from "./markdown";

function readFile(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => {
      const dataUrl = String(r.result);
      resolve({
        name: file.name || "file",
        mimeType: file.type || "application/octet-stream",
        base64: dataUrl.split(",")[1] || "",
        dataUrl,
        isImage: (file.type || "").startsWith("image/"),
      });
    };
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

// Fetch same-host (protected) images with the Bearer key → object URL; pass
// through cross-host/absolute images untouched.
function AuthImg({ src, host, apiKey }) {
  const [url, setUrl] = useState(null);
  useEffect(() => {
    let revoked = false;
    let obj = null;
    if (!src) return undefined;
    // Only attach the Bearer key for images on the EXACT paired origin — compare
    // parsed origins, not a string prefix, so a look-alike host (e.g.
    // https://paired-host.evil.net/…) injected via the model can't capture the key.
    let sameOrigin = false;
    try {
      sameOrigin = new URL(src, host).origin === new URL(host).origin;
    } catch {
      sameOrigin = false;
    }
    if (!sameOrigin) {
      setUrl(src);
      return undefined;
    }
    fetch(src, { headers: { Authorization: `Bearer ${apiKey}` } })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error("img"))))
      .then((b) => {
        if (!revoked) {
          obj = URL.createObjectURL(b);
          setUrl(obj);
        }
      })
      .catch(() => setUrl(null));
    return () => {
      revoked = true;
      if (obj) URL.revokeObjectURL(obj);
    };
  }, [src, host, apiKey]);
  if (!url) return null;
  return <img src={url} alt="" className="md-img" />;
}

function Markdown({ text, host, apiKey }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw, rehypeSanitize]}
      components={{ img: (props) => <AuthImg {...props} host={host} apiKey={apiKey} /> }}
    >
      {rewriteRelativeImages(text, host)}
    </ReactMarkdown>
  );
}

export default function Chat({ creds, onUnpair }) {
  const { host, projectId, projectName, apiKey } = creds;
  const [messages, setMessages] = useState([]); // {role, text, images?, files?}
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState("");
  const [attachments, setAttachments] = useState([]);
  const [sending, setSending] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const endRef = useRef(null);
  const camRef = useRef(null);
  const imgRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const setLastAssistant = (txt) =>
    setMessages((m) => {
      const out = m.slice();
      for (let i = out.length - 1; i >= 0; i--) {
        if (out[i].role === "assistant") {
          out[i] = { ...out[i], text: txt };
          break;
        }
      }
      return out;
    });

  const onPick = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    setMenuOpen(false);
    if (!files.length) return;
    const read = await Promise.all(files.map(readFile));
    setAttachments((a) => [...a, ...read]);
  };

  const newConversation = () => {
    if (sending) return;
    setMessages([]);
    setConversationId(null);
  };

  const doSend = async () => {
    const text = input.trim();
    if ((!text && attachments.length === 0) || sending) return;

    const sent = attachments;
    const userMsg = {
      role: "user",
      text,
      images: sent.filter((a) => a.isImage).map((a) => a.dataUrl),
      files: sent.filter((a) => !a.isImage).map((a) => a.name),
    };
    setMessages((m) => [...m, userMsg, { role: "assistant", text: "" }]);
    setInput("");
    setAttachments([]);
    setSending(true);

    const image = sent.find((a) => a.isImage)?.dataUrl || null;
    const files = sent.map((a) => ({ name: a.name, content: a.base64, mime_type: a.mimeType }));
    let acc = "";

    try {
      const newId = await streamChat({
        host,
        projectId,
        apiKey,
        question: text,
        id: conversationId,
        image,
        files,
        onDelta: (d) => {
          acc += d;
          setLastAssistant(stripThink(acc));
        },
        onFinal: (answer, fid) => {
          if (fid) setConversationId(fid);
          setLastAssistant(stripThink(answer));
        },
      });
      if (newId) setConversationId(newId);
    } catch (e) {
      if (e instanceof AuthError) {
        setLastAssistant("Session expired. Please re-pair from your project's Mobile tab.");
        onUnpair();
      } else {
        setLastAssistant("Network error: " + (e?.message || e));
      }
    } finally {
      setSending(false);
    }
  };

  const canSend = (!!input.trim() || attachments.length > 0) && !sending;

  return (
    <div className="chat">
      <header className="topbar">
        <button className="iconbtn logo" title="New conversation" onClick={newConversation}>
          <img src="/mobile/icons/icon-192.png" alt="New conversation" />
        </button>
        <div className="title">{projectName || "RESTai"}</div>
        <button className="iconbtn" title="Unpair" onClick={onUnpair}>⎋</button>
      </header>

      <main className="messages">
        {messages.length === 0 && (
          <div className="empty">
            <div className="empty-avatar">🤖</div>
            <div className="empty-text">How can I help you?</div>
          </div>
        )}
        {messages.map((m, i) => {
          const isLast = i === messages.length - 1;
          if (m.role === "user") {
            return (
              <div className="row user" key={i}>
                <div className="bubble user-bubble">
                  {m.images?.map((src, k) => <img key={k} className="att-img" src={src} alt="" />)}
                  {m.files?.map((name, k) => <span key={k} className="att-chip">{name}</span>)}
                  {m.text && <div className="user-text">{m.text}</div>}
                </div>
              </div>
            );
          }
          return (
            <div className="row assistant" key={i}>
              <div className="avatar">🤖</div>
              <div className="bubble assistant-bubble">
                {m.text === "" && isLast && sending ? (
                  <div className="typing"><span /><span /><span /></div>
                ) : (
                  <>
                    <Markdown text={m.text} host={host} apiKey={apiKey} />
                    {m.text !== "" && (
                      <button
                        className="copybtn"
                        title="Copy"
                        onClick={() => navigator.clipboard?.writeText(m.text)}
                      >
                        Copy
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </main>

      {attachments.length > 0 && (
        <div className="att-tray">
          {attachments.map((a, i) => (
            <span className="att-pill" key={i}>
              {a.isImage && <img src={a.dataUrl} alt="" />}
              <span className="att-name">{a.name}</span>
              <button onClick={() => setAttachments((x) => x.filter((_, k) => k !== i))}>×</button>
            </span>
          ))}
        </div>
      )}

      <footer className="composer">
        <div className="plus-wrap">
          <button className="iconbtn" title="Attach" onClick={() => setMenuOpen((o) => !o)}>+</button>
          {menuOpen && (
            <div className="menu">
              <button onClick={() => camRef.current?.click()}>Take photo</button>
              <button onClick={() => imgRef.current?.click()}>Choose image</button>
              <button onClick={() => fileRef.current?.click()}>Upload file</button>
            </div>
          )}
        </div>
        <textarea
          className="input"
          placeholder="Message"
          rows={1}
          value={input}
          disabled={sending}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              doSend();
            }
          }}
        />
        <button className="sendbtn" disabled={!canSend} onClick={doSend} title="Send">↑</button>
      </footer>

      <input ref={camRef} type="file" accept="image/*" capture="environment" hidden onChange={onPick} />
      <input ref={imgRef} type="file" accept="image/*" hidden onChange={onPick} />
      <input ref={fileRef} type="file" hidden onChange={onPick} />
    </div>
  );
}
