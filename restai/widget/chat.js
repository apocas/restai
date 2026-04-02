(function () {
  "use strict";

  // --- Config from script tag ---
  const scriptTag = document.currentScript;
  if (!scriptTag) return;

  const cfg = {
    projectId: scriptTag.getAttribute("data-project-id"),
    apiKey: scriptTag.getAttribute("data-api-key"),
    title: scriptTag.getAttribute("data-title") || "AI Assistant",
    subtitle: scriptTag.getAttribute("data-subtitle") || "Ask me anything",
    primaryColor: scriptTag.getAttribute("data-primary-color") || "#6366f1",
    textColor: scriptTag.getAttribute("data-text-color") || "#ffffff",
    position: scriptTag.getAttribute("data-position") || "right",
    welcomeMessage: scriptTag.getAttribute("data-welcome-message") || "",
    avatarUrl: scriptTag.getAttribute("data-avatar-url") || "",
    stream: scriptTag.getAttribute("data-stream") === "true",
    server: scriptTag.getAttribute("data-server") || scriptTag.src.replace(/\/widget\/chat\.js.*$/, ""),
  };

  if (!cfg.projectId || !cfg.apiKey) {
    console.error("RESTai Widget: data-project-id and data-api-key are required.");
    return;
  }

  // --- State ---
  let isOpen = false;
  let chatId = null;
  let isStreaming = false;
  const messages = [];

  // --- Shadow DOM ---
  const host = document.createElement("div");
  host.id = "restai-widget-host";
  document.body.appendChild(host);
  const shadow = host.attachShadow({ mode: "closed" });

  // --- Styles ---
  const pos = cfg.position === "left" ? "left" : "right";
  const otherPos = pos === "left" ? "right" : "left";

  const style = document.createElement("style");
  style.textContent = `
    *,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
    :host{all:initial;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;font-size:14px;line-height:1.5;color:#1a1a2e}

    .restai-bubble{
      position:fixed;bottom:24px;${pos}:24px;
      width:56px;height:56px;border-radius:50%;
      background:${cfg.primaryColor};color:${cfg.textColor};
      border:none;cursor:pointer;
      box-shadow:0 4px 16px rgba(0,0,0,.2);
      display:flex;align-items:center;justify-content:center;
      transition:transform .2s,box-shadow .2s;z-index:2147483646;
    }
    .restai-bubble:hover{transform:scale(1.08);box-shadow:0 6px 24px rgba(0,0,0,.3)}
    .restai-bubble svg{width:28px;height:28px;fill:currentColor}

    .restai-panel{
      position:fixed;bottom:92px;${pos}:24px;${otherPos}:auto;
      width:380px;max-height:560px;height:70vh;
      background:#fff;border-radius:16px;
      box-shadow:0 12px 48px rgba(0,0,0,.15);
      display:flex;flex-direction:column;
      z-index:2147483647;
      opacity:0;transform:translateY(16px) scale(.96);
      pointer-events:none;
      transition:opacity .25s ease,transform .25s ease;
      overflow:hidden;
    }
    .restai-panel.open{opacity:1;transform:translateY(0) scale(1);pointer-events:auto}

    .restai-header{
      background:${cfg.primaryColor};color:${cfg.textColor};
      padding:16px 20px;display:flex;align-items:center;gap:12px;
      flex-shrink:0;
    }
    .restai-header-avatar{
      width:36px;height:36px;border-radius:50%;
      background:rgba(255,255,255,.2);
      display:flex;align-items:center;justify-content:center;
      overflow:hidden;flex-shrink:0;
    }
    .restai-header-avatar img{width:100%;height:100%;object-fit:cover}
    .restai-header-info{flex:1;min-width:0}
    .restai-header-title{font-weight:700;font-size:15px;line-height:1.2}
    .restai-header-subtitle{font-size:12px;opacity:.8;line-height:1.3}
    .restai-close{background:none;border:none;color:${cfg.textColor};cursor:pointer;padding:4px;opacity:.7;transition:opacity .2s}
    .restai-close:hover{opacity:1}
    .restai-close svg{width:20px;height:20px;fill:currentColor}

    .restai-messages{
      flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px;
      scroll-behavior:smooth;
    }

    .restai-msg{display:flex;gap:8px;max-width:88%}
    .restai-msg.bot{align-self:flex-start}
    .restai-msg.user{align-self:flex-end;flex-direction:row-reverse}
    .restai-msg-avatar{
      width:28px;height:28px;border-radius:50%;flex-shrink:0;
      background:${cfg.primaryColor};color:${cfg.textColor};
      display:flex;align-items:center;justify-content:center;
      font-size:12px;font-weight:700;overflow:hidden;margin-top:2px;
    }
    .restai-msg-avatar img{width:100%;height:100%;object-fit:cover}
    .restai-msg.user .restai-msg-avatar{background:#e0e0e0;color:#555}

    .restai-msg-content{
      padding:10px 14px;border-radius:14px;font-size:14px;line-height:1.55;
      word-wrap:break-word;overflow-wrap:break-word;
    }
    .restai-msg.bot .restai-msg-content{background:#f0f0f5;color:#1a1a2e;border-bottom-left-radius:4px}
    .restai-msg.user .restai-msg-content{background:${cfg.primaryColor};color:${cfg.textColor};border-bottom-right-radius:4px}

    .restai-msg-content code{
      background:rgba(0,0,0,.08);padding:1px 5px;border-radius:4px;
      font-family:'SF Mono',Monaco,Consolas,monospace;font-size:13px;
    }
    .restai-msg-content pre{
      background:#1e1e2e;color:#cdd6f4;padding:12px;border-radius:8px;
      overflow-x:auto;margin:8px 0;font-size:13px;line-height:1.4;
    }
    .restai-msg-content pre code{background:none;padding:0;color:inherit}
    .restai-msg-content a{color:${cfg.primaryColor};text-decoration:underline}
    .restai-msg-content p{margin:6px 0}
    .restai-msg-content p:first-child{margin-top:0}
    .restai-msg-content p:last-child{margin-bottom:0}
    .restai-msg-content ul,.restai-msg-content ol{margin:6px 0;padding-left:20px}

    .restai-typing{display:flex;gap:4px;padding:4px 0}
    .restai-typing span{width:6px;height:6px;border-radius:50%;background:#999;animation:restai-bounce .6s ease infinite}
    .restai-typing span:nth-child(2){animation-delay:.15s}
    .restai-typing span:nth-child(3){animation-delay:.3s}
    @keyframes restai-bounce{0%,100%{opacity:.3;transform:translateY(0)}50%{opacity:1;transform:translateY(-4px)}}

    .restai-input-area{
      padding:12px 16px;border-top:1px solid #eee;display:flex;gap:8px;
      flex-shrink:0;background:#fff;
    }
    .restai-input{
      flex:1;border:1px solid #ddd;border-radius:24px;padding:10px 16px;
      font-size:14px;outline:none;resize:none;
      font-family:inherit;line-height:1.4;
      max-height:100px;overflow-y:auto;
    }
    .restai-input:focus{border-color:${cfg.primaryColor}}
    .restai-input::placeholder{color:#aaa}
    .restai-send{
      width:40px;height:40px;border-radius:50%;border:none;
      background:${cfg.primaryColor};color:${cfg.textColor};
      cursor:pointer;display:flex;align-items:center;justify-content:center;
      flex-shrink:0;transition:opacity .2s;
    }
    .restai-send:hover{opacity:.85}
    .restai-send:disabled{opacity:.4;cursor:default}
    .restai-send svg{width:18px;height:18px;fill:currentColor}

    .restai-powered{
      text-align:center;padding:6px;font-size:11px;color:#aaa;
      background:#fafafa;border-top:1px solid #f0f0f0;
    }
    .restai-powered a{color:#888;text-decoration:none}
    .restai-powered a:hover{color:#555}

    @media(max-width:500px){
      .restai-panel{width:calc(100vw - 16px);${pos}:8px;bottom:80px;max-height:calc(100vh - 100px);border-radius:12px}
      .restai-bubble{bottom:16px;${pos}:16px}
    }
  `;
  shadow.appendChild(style);

  // --- Icons ---
  const ICON_CHAT = '<svg viewBox="0 0 24 24"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H5.17L4 17.17V4h16v12z"/><path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/></svg>';
  const ICON_CLOSE = '<svg viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>';
  const ICON_SEND = '<svg viewBox="0 0 24 24"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>';
  const ICON_BOT = '<svg viewBox="0 0 24 24"><path d="M12 2a2 2 0 012 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 017 7h1a1 1 0 011 1v3a1 1 0 01-1 1h-1v1a2 2 0 01-2 2H6a2 2 0 01-2-2v-1H3a1 1 0 01-1-1v-3a1 1 0 011-1h1a7 7 0 017-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 012-2zM9 14a1 1 0 100 2 1 1 0 000-2zm6 0a1 1 0 100 2 1 1 0 000-2z"/></svg>';

  // --- Markdown-lite ---
  function renderMarkdown(text) {
    let html = text
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => `<pre><code>${code.trim()}</code></pre>`)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    html = html.split(/\n\n+/).map(p => {
      p = p.trim();
      if (p.startsWith("<pre>") || p.startsWith("<ul>") || p.startsWith("<ol>")) return p;
      return `<p>${p.replace(/\n/g, "<br>")}</p>`;
    }).join("");
    return html;
  }

  // --- Build DOM ---
  const container = document.createElement("div");

  // Bubble
  const bubble = document.createElement("button");
  bubble.className = "restai-bubble";
  bubble.innerHTML = ICON_CHAT;
  bubble.setAttribute("aria-label", "Open chat");
  container.appendChild(bubble);

  // Panel
  const panel = document.createElement("div");
  panel.className = "restai-panel";

  const avatarHtml = cfg.avatarUrl
    ? `<img src="${cfg.avatarUrl}" alt="">`
    : ICON_BOT.replace('viewBox', 'style="width:20px;height:20px;fill:' + cfg.textColor + '" viewBox');

  panel.innerHTML = `
    <div class="restai-header">
      <div class="restai-header-avatar">${avatarHtml}</div>
      <div class="restai-header-info">
        <div class="restai-header-title">${cfg.title}</div>
        <div class="restai-header-subtitle">${cfg.subtitle}</div>
      </div>
      <button class="restai-close" aria-label="Close chat">${ICON_CLOSE}</button>
    </div>
    <div class="restai-messages" id="restai-msgs"></div>
    <div class="restai-input-area">
      <textarea class="restai-input" placeholder="Type a message..." rows="1" id="restai-input"></textarea>
      <button class="restai-send" id="restai-send" aria-label="Send">${ICON_SEND}</button>
    </div>
    <div class="restai-powered"><a href="https://github.com/apocas/restai" target="_blank" rel="noopener">Powered by RESTai</a></div>
  `;
  container.appendChild(panel);
  shadow.appendChild(container);

  const msgsEl = shadow.getElementById("restai-msgs");
  const inputEl = shadow.getElementById("restai-input");
  const sendBtn = shadow.getElementById("restai-send");
  const closeBtn = panel.querySelector(".restai-close");

  // --- Toggle ---
  function toggle() {
    isOpen = !isOpen;
    panel.classList.toggle("open", isOpen);
    bubble.innerHTML = isOpen ? ICON_CLOSE : ICON_CHAT;
    if (isOpen) {
      inputEl.focus();
      scrollToBottom();
    }
  }
  bubble.addEventListener("click", toggle);
  closeBtn.addEventListener("click", toggle);

  // --- Add welcome message ---
  if (cfg.welcomeMessage) {
    messages.push({ role: "bot", content: cfg.welcomeMessage });
    renderMessages();
  }

  // --- Render messages ---
  function renderMessages(showTyping, streamingText) {
    let html = "";
    for (const msg of messages) {
      const isBot = msg.role === "bot";
      const avatarContent = isBot
        ? (cfg.avatarUrl ? `<img src="${cfg.avatarUrl}" alt="">` : ICON_BOT.replace('viewBox', 'style="width:14px;height:14px;fill:' + cfg.textColor + '" viewBox'))
        : '<span style="font-size:12px">You</span>';
      html += `<div class="restai-msg ${msg.role}">
        <div class="restai-msg-avatar">${avatarContent}</div>
        <div class="restai-msg-content">${isBot ? renderMarkdown(msg.content) : escapeHtml(msg.content)}</div>
      </div>`;
    }
    if (showTyping || streamingText) {
      const avatarContent = cfg.avatarUrl ? `<img src="${cfg.avatarUrl}" alt="">` : ICON_BOT.replace('viewBox', 'style="width:14px;height:14px;fill:' + cfg.textColor + '" viewBox');
      html += `<div class="restai-msg bot">
        <div class="restai-msg-avatar">${avatarContent}</div>
        <div class="restai-msg-content">${streamingText ? renderMarkdown(streamingText) : '<div class="restai-typing"><span></span><span></span><span></span></div>'}</div>
      </div>`;
    }
    msgsEl.innerHTML = html;
    scrollToBottom();
  }

  function escapeHtml(t) {
    return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/\n/g, "<br>");
  }

  function scrollToBottom() {
    requestAnimationFrame(() => { msgsEl.scrollTop = msgsEl.scrollHeight; });
  }

  // --- Send message ---
  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || isStreaming) return;

    messages.push({ role: "user", content: text });
    inputEl.value = "";
    inputEl.style.height = "auto";
    renderMessages(true);
    isStreaming = true;
    sendBtn.disabled = true;

    try {
      const body = { question: text };
      if (chatId) body.id = chatId;
      if (cfg.stream) body.stream = true;

      const headers = {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${cfg.apiKey}`,
      };
      if (cfg.stream) headers["Accept"] = "text/event-stream";

      const resp = await fetch(`${cfg.server}/projects/${cfg.projectId}/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      });

      if (!resp.ok) {
        const err = await resp.text();
        messages.push({ role: "bot", content: `Error: ${resp.status} — ${err}` });
        renderMessages();
        return;
      }

      if (cfg.stream) {
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let accumulated = "";
        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.answer !== undefined && data.type !== undefined) {
                  chatId = data.id || chatId;
                } else if (data.text !== undefined) {
                  accumulated += data.text;
                  renderMessages(false, accumulated);
                }
              } catch (e) {}
            }
          }
        }
        messages.push({ role: "bot", content: accumulated || "No response." });
      } else {
        const data = await resp.json();
        chatId = data.id || chatId;
        messages.push({ role: "bot", content: data.answer || "No response." });
      }
      renderMessages();

    } catch (err) {
      messages.push({ role: "bot", content: `Connection error: ${err.message}` });
      renderMessages();
    } finally {
      isStreaming = false;
      sendBtn.disabled = false;
    }
  }

  // --- Event listeners ---
  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 100) + "px";
  });
})();
