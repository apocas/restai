import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  Box, Fab, TextField, Tooltip, Typography, Chip, styled, IconButton,
} from "@mui/material";
import { Send, Stop, AttachFile, DeleteSweep, CallSplit, Close } from "@mui/icons-material";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import MessageBubble from "./MessageBubble";

const HiddenInput = styled("input")({ display: "none" });

const url = process.env.REACT_APP_RESTAI_API_URL || "";

// Map a status code + optional server detail to user-friendly copy.
// Called from both the streaming and non-streaming error paths so the
// user sees consistent messaging regardless of transport. Translated
// via `t()` so every locale can re-word these from `chat.error.*`.
function formatChatError(t, status, detail) {
  const d = (detail || "").toString().trim();
  switch (status) {
    case 401: return t("chat.error.sessionExpired");
    case 402: return t("chat.error.budgetExhausted");
    case 403: return d || t("chat.error.forbidden");
    case 404: return t("chat.error.notFound");
    case 413: return t("chat.error.tooLarge");
    case 422: return d ? t("chat.error.invalidDetail", { detail: d }) : t("chat.error.invalid");
    case 429:
      if (d && d.toLowerCase().includes("quota"))
        return t("chat.error.quotaReached", { detail: d });
      return t("chat.error.rateLimit");
    case 500: return t("chat.error.internal");
    case 502:
    case 503:
      return t("chat.error.overloaded");
    case 504: return t("chat.error.timeout");
    default:
      if (d) return t("chat.error.default", { detail: d });
      return t("chat.error.generic");
  }
}

export default function ChatPanel({ project, systemOverride, sharedQuestion, onQuestionSent, chatMode = false, compact = false, streaming = false, context = null }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  // Single attachments array. Entries look like:
  //   { name, size, mime_type, contentBase64, isImage, dataUrl? }
  // `dataUrl` is only set for images (for inline preview) and never sent
  // over the wire — the backend only needs `contentBase64`.
  const [files, setFiles] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const scrollRef = useRef(null);
  // AbortController for the in-flight streaming fetch. Kept in a ref so
  // the Stop button can access the live controller without triggering
  // re-renders on each stream chunk.
  const streamAbortRef = useRef(null);

  // Branching: each branch is { name: string, messages: array }
  // branches is empty when there's only one thread (no branching yet)
  const [branches, setBranches] = useState([]);
  const [activeBranchIdx, setActiveBranchIdx] = useState(-1); // -1 = no branches

  // Save current messages into the active branch
  const saveCurrentBranch = useCallback((currentMessages) => {
    if (activeBranchIdx >= 0) {
      setBranches(prev => prev.map((b, i) => i === activeBranchIdx ? { ...b, messages: currentMessages } : b));
    }
  }, [activeBranchIdx]);

  // Sync messages into active branch whenever they change
  useEffect(() => {
    if (activeBranchIdx >= 0 && messages.length > 0) {
      saveCurrentBranch(messages);
    }
  }, [messages]);

  const handleBranch = useCallback((messageIndex) => {
    const branchPoint = messages.slice(0, messageIndex + 1);

    if (branches.length === 0) {
      // First branch: create "Main" (full current conversation) + the new branch
      const mainBranch = { name: "Main", messages: [...messages] };
      const newNum = 1;
      const newBranch = { name: `Branch ${newNum}`, messages: [...branchPoint] };
      setBranches([mainBranch, newBranch]);
      setMessages([...branchPoint]);
      setActiveBranchIdx(1);
    } else {
      // Save current branch, then create a new one
      const newNum = branches.length;
      const newBranch = { name: `Branch ${newNum}`, messages: [...branchPoint] };
      setBranches(prev => {
        const updated = prev.map((b, i) => i === activeBranchIdx ? { ...b, messages: [...messages] } : b);
        updated.push(newBranch);
        return updated;
      });
      setMessages([...branchPoint]);
      setActiveBranchIdx(branches.length); // index of the newly pushed branch
    }
  }, [messages, branches, activeBranchIdx]);

  const switchBranch = useCallback((targetIdx) => {
    if (targetIdx === activeBranchIdx) return;
    // Save current, load target
    setBranches(prev => {
      const updated = [...prev];
      if (activeBranchIdx >= 0 && updated[activeBranchIdx]) {
        updated[activeBranchIdx] = { ...updated[activeBranchIdx], messages: [...messages] };
      }
      return updated;
    });
    setMessages([...branches[targetIdx].messages]);
    setActiveBranchIdx(targetIdx);
  }, [messages, branches, activeBranchIdx]);

  const deleteBranch = useCallback((targetIdx) => {
    setBranches(prev => {
      const updated = prev.filter((_, i) => i !== targetIdx);
      if (updated.length <= 1) {
        // Only one branch left, dissolve branching
        if (updated.length === 1) setMessages([...updated[0].messages]);
        setActiveBranchIdx(-1);
        return [];
      }
      // Adjust active index
      let newActive = activeBranchIdx;
      if (targetIdx === activeBranchIdx) {
        newActive = Math.min(targetIdx, updated.length - 1);
        setMessages([...updated[newActive].messages]);
      } else if (targetIdx < activeBranchIdx) {
        newActive = activeBranchIdx - 1;
      }
      setActiveBranchIdx(newActive);
      return updated;
    });
  }, [activeBranchIdx]);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingText]);

  // Handle shared question from compare mode
  useEffect(() => {
    if (sharedQuestion && sharedQuestion.text) {
      // Legacy sharedQuestion.image (data URL) is converted into a single
      // image attachment so the backend's unified router picks it up.
      const attach = sharedQuestion.image
        ? [{
            name: "image.png",
            size: 0,
            mime_type: "image/png",
            contentBase64: sharedQuestion.image.includes("base64,")
              ? sharedQuestion.image.split(",")[1]
              : sharedQuestion.image,
            isImage: true,
            dataUrl: sharedQuestion.image.startsWith("data:") ? sharedQuestion.image : `data:image/png;base64,${sharedQuestion.image}`,
          }]
        : null;
      sendMessage(sharedQuestion.text, attach);
    }
  }, [sharedQuestion]);

  const sendMessageStream = useCallback(async (questionText, attachments) => {
    const body = { question: questionText, stream: true };
    if (attachments && attachments.length > 0) {
      body.files = attachments.map((f) => ({ name: f.name, content: f.contentBase64, mime_type: f.mime_type }));
    }
    if (systemOverride) body.system = systemOverride;
    if (context) body.context = context;

    const endpoint = chatMode ? "chat" : "question";
    if (chatMode && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.id) body.id = lastMsg.id;
    }

    // Preview refs for the chat log. Keep the image dataUrl inline, but strip
    // contentBase64 so we don't hold onto megabytes of attachment bytes.
    const fileRefs = (attachments || []).map((f) => ({
      name: f.name, size: f.size, mime_type: f.mime_type,
      isImage: f.isImage, dataUrl: f.isImage ? f.dataUrl : null,
    }));
    setMessages(prev => [...prev, {
      question: questionText, answer: null, sources: [],
      _files: fileRefs.length ? fileRefs : null,
    }]);
    setStreamingText("");

    let accumulated = "";
    let finalOutput = null;

    // Captured by onopen when the upstream returns a non-2xx before the
    // stream ever starts. Gets fed to formatChatError below so the
    // error message matches the actual HTTP status.
    let httpStatus = 0;
    let httpDetail = "";

    // Fresh abort controller per stream. handleStopStreaming() calls
    // abort() on this; the onerror handler checks the `aborted` flag
    // so we don't show an error bubble for an intentional cancel.
    const controller = new AbortController();
    streamAbortRef.current = controller;

    await fetchEventSource(url + `/projects/${project.id}/${endpoint}`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Authorization": "Basic " + auth.user.token,
      },
      body: JSON.stringify(body),
      async onopen(response) {
        if (!response.ok) {
          httpStatus = response.status;
          try {
            const data = await response.json();
            httpDetail = typeof data.detail === "string" ? data.detail : "";
          } catch {}
          // Throwing here jumps to onerror with this exception.
          throw new Error(`http ${response.status}`);
        }
      },
      onmessage(ev) {
        try {
          const data = JSON.parse(ev.data);
          if (data.answer !== undefined && data.type !== undefined) {
            // Final output with full metadata
            finalOutput = data;
          } else if (data.text !== undefined) {
            accumulated += data.text;
            setStreamingText(accumulated);
          }
        } catch (e) {
          // Non-JSON chunk, ignore
        }
      },
      onclose() {
        setStreamingText("");
        if (finalOutput) {
          setMessages(prev => {
            const updated = [...prev];
            const placeholder = updated[updated.length - 1] || {};
            updated[updated.length - 1] = { ...finalOutput, _files: placeholder._files };
            return updated;
          });
          if (finalOutput.guard) {
            toast.warning(t("chat.guardHit"), { position: "top-right" });
          }
          if (project.type === "rag" && finalOutput.sources && finalOutput.sources.length === 0) {
            toast.warning(t("chat.ragNoSources"), { position: "top-right" });
          }
        } else if (accumulated) {
          setMessages(prev => {
            const updated = [...prev];
            const placeholder = updated[updated.length - 1] || {};
            const prevId = updated.length > 1 ? updated[updated.length - 2]?.id : undefined;
            updated[updated.length - 1] = {
              question: questionText,
              answer: accumulated,
              sources: [],
              id: prevId,
              _files: placeholder._files,
            };
            return updated;
          });
        }
        setIsLoading(false);
        setFiles([]);
        streamAbortRef.current = null;
        if (onQuestionSent) onQuestionSent();
      },
      onerror(err) {
        setStreamingText("");
        // Intentional user abort — keep whatever text we accumulated
        // as the final answer and exit quietly, no error bubble, no
        // toast. Aborting via AbortController surfaces here as a
        // DOMException with name "AbortError" (or the signal flagged).
        const aborted = controller.signal.aborted || (err && err.name === "AbortError");
        if (aborted) {
          setMessages(prev => {
            const updated = [...prev];
            const prevId = updated.length > 1 ? updated[updated.length - 2]?.id : undefined;
            const placeholder = updated[updated.length - 1] || {};
            updated[updated.length - 1] = {
              question: questionText,
              answer: accumulated ? `${accumulated}\n\n_${t("chat.stoppedSuffix")}_` : `_${t("chat.stoppedSuffix")}_`,
              sources: [],
              id: prevId,
              _files: placeholder._files,
            };
            return updated;
          });
          setIsLoading(false);
          setFiles([]);
          streamAbortRef.current = null;
          throw err; // Stop fetchEventSource from retrying
        }

        const msg = formatChatError(t, httpStatus, httpDetail);
        setMessages(prev => {
          const updated = [...prev];
          const prevId = updated.length > 1 ? updated[updated.length - 2]?.id : undefined;
          updated[updated.length - 1] = { question: questionText, answer: msg, sources: [], id: prevId };
          return updated;
        });
        // Toast for anything actionable (rate limit / budget / quota /
        // auth). Leaves the inline bubble as the record of what went
        // wrong for less-actionable cases (500/unknown).
        if ([401, 402, 413, 429].includes(httpStatus)) {
          toast.error(msg, { position: "top-right" });
        }
        setIsLoading(false);
        setFiles([]);
        streamAbortRef.current = null;
        throw err; // Stop reconnecting
      },
    });
  }, [project.id, auth.user.token, systemOverride, chatMode, messages, onQuestionSent, context]);

  const sendMessage = useCallback(async (text, attachments) => {
    if (isLoading) return;
    if (!text && !(attachments && attachments.length)) return;

    const questionText = text || "";
    setIsLoading(true);
    setInputText("");

    if (streaming) {
      try {
        await sendMessageStream(questionText, attachments);
      } catch (e) {
        setIsLoading(false);
        setFiles([]);
      }
      return;
    }

    // Non-streaming path
    const fileRefs = (attachments || []).map((f) => ({
      name: f.name, size: f.size, mime_type: f.mime_type,
      isImage: f.isImage, dataUrl: f.isImage ? f.dataUrl : null,
    }));
    setMessages(prev => [...prev, {
      question: questionText, answer: null, sources: [],
      _files: fileRefs.length ? fileRefs : null,
    }]);

    const body = { question: questionText };
    if (attachments && attachments.length > 0) {
      body.files = attachments.map((f) => ({ name: f.name, content: f.contentBase64, mime_type: f.mime_type }));
    }
    if (systemOverride) body.system = systemOverride;
    if (context) body.context = context;

    const endpoint = chatMode ? "chat" : "question";
    if (chatMode && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.id) body.id = lastMsg.id;
    }

    try {
      const response = await api.post(
        `/projects/${project.id}/${endpoint}`,
        body,
        auth.user.token
      );
      setMessages(prev => {
        const updated = [...prev];
        const placeholder = updated[updated.length - 1] || {};
        updated[updated.length - 1] = { ...response, _files: placeholder._files };
        return updated;
      });
      if (response.guard) {
        toast.warning("This question hit the prompt guard.", { position: "top-right" });
      }
      if (project.type === "rag" && response.sources && response.sources.length === 0) {
        toast.warning("No sources found. Try decreasing the score cutoff.", { position: "top-right" });
      }
    } catch (e) {
      // e is an ApiError (from api.js) — carries .status and .detail.
      const msg = formatChatError(t, e && e.status, e && e.detail);
      setMessages(prev => {
        const updated = [...prev];
        const prevId = updated.length > 1 ? updated[updated.length - 2]?.id : undefined;
        updated[updated.length - 1] = {
          question: questionText,
          answer: msg,
          sources: [],
          id: prevId,
        };
        return updated;
      });
      if ([401, 402, 413, 429].includes(e && e.status)) {
        toast.error(msg, { position: "top-right" });
      }
    } finally {
      setIsLoading(false);
      setFiles([]);
      if (onQuestionSent) onQuestionSent();
    }
  }, [isLoading, streaming, project.id, auth.user.token, systemOverride, chatMode, messages, onQuestionSent, sendMessageStream, context]);

  const handleSend = () => {
    const text = inputText.trim();
    const attachments = files;
    if (text || (attachments && attachments.length)) {
      sendMessage(text, attachments);
    }
  };

  // Stop the in-flight stream. onerror handles the aborted branch and
  // keeps whatever text was accumulated. No-op when nothing's in flight.
  const handleStopStreaming = () => {
    const controller = streamAbortRef.current;
    if (controller) {
      try { controller.abort(); } catch {}
    }
  };

  const handleKeyDown = (e) => {
    // `e.isComposing` (or keyCode 229) means an IME is mid-composition —
    // typical for CJK input methods where Enter confirms the candidate
    // character, NOT the message. Also bail on Shift+Enter (explicit
    // newline per the Slack/Discord convention).
    if (e.key !== "Enter" || e.shiftKey) return;
    if (e.isComposing || e.keyCode === 229) return;
    e.preventDefault();
    handleSend();
  };

  const MAX_FILE_MB = 20;

  const fileIsImage = (file) => {
    const t = (file.type || "").toLowerCase();
    if (t.startsWith("image/")) return true;
    const n = (file.name || "").toLowerCase();
    return /\.(png|jpe?g|gif|webp|bmp|svg)$/.test(n);
  };

  const handleAttachFiles = async (e) => {
    const chosen = Array.from(e.target.files || []);
    e.target.value = "";
    if (!chosen.length) return;
    const remaining = 10 - files.length;
    if (remaining <= 0) {
      toast.warning("Max 10 files per message.", { position: "top-right" });
      return;
    }
    const accepted = [];
    for (const file of chosen.slice(0, remaining)) {
      if (file.size > MAX_FILE_MB * 1024 * 1024) {
        toast.warning(`${file.name} exceeds ${MAX_FILE_MB} MB limit.`, { position: "top-right" });
        continue;
      }
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result || "");
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      const idx = dataUrl.indexOf(",");
      const b64 = idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
      const isImage = fileIsImage(file);
      accepted.push({
        name: file.name,
        size: file.size,
        mime_type: file.type || null,
        contentBase64: b64,
        isImage,
        dataUrl: isImage ? dataUrl : null,
      });
    }
    if (accepted.length) setFiles((prev) => [...prev, ...accepted]);
  };

  const removeFile = (idx) => setFiles((prev) => prev.filter((_, i) => i !== idx));

  const handleClear = () => {
    setMessages([]);
    setStreamingText("");
    setFiles([]);
    setBranches([]);
    setActiveBranchIdx(-1);
  };

  const showUpload = project.type === "agent" || project.type === "block";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: compact ? 500 : 600 }}>
      {/* Branch tabs */}
      {branches.length > 0 && (
        <Box sx={{ display: "flex", gap: 0.5, px: 2, py: 1, borderBottom: 1, borderColor: "divider", flexWrap: "wrap", alignItems: "center" }}>
          <CallSplit sx={{ fontSize: 16, color: "text.secondary", mr: 0.5 }} />
          {branches.map((branch, idx) => (
            <Chip
              key={idx}
              label={branch.name}
              size="small"
              color={idx === activeBranchIdx ? "primary" : "default"}
              variant={idx === activeBranchIdx ? "filled" : "outlined"}
              onClick={() => switchBranch(idx)}
              onDelete={branches.length > 2 ? () => deleteBranch(idx) : undefined}
              sx={{ fontSize: "0.75rem", height: 26 }}
            />
          ))}
        </Box>
      )}

      {/* Messages */}
      <Box sx={{ flex: 1, overflow: "auto" }} ref={scrollRef}>
          <Box sx={{ p: 2 }}>
            {messages.length === 0 && (
              <Box sx={{ textAlign: "center", mt: 4, color: "text.secondary" }}>
                <Typography variant="body2" sx={{ fontStyle: "italic" }}>
                  {systemOverride
                    ? systemOverride.substring(0, 200) + (systemOverride.length > 200 ? "..." : "")
                    : project.system
                      ? project.system.substring(0, 200) + (project.system.length > 200 ? "..." : "")
                      : t("chat.getStarted")}
                </Typography>
                {project.default_prompt && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    Suggested: {project.default_prompt}
                  </Typography>
                )}
              </Box>
            )}
            {messages.map((msg, i) => (
              <MessageBubble
                key={`${activeBranchIdx}-${i}`}
                message={msg}
                onBranch={chatMode && msg.answer ? () => handleBranch(i) : undefined}
              />
            ))}
            {streamingText && (
              <MessageBubble message={{ question: null, answer: streamingText, sources: [] }} />
            )}
          </Box>
      </Box>

      {/* Attachments preview — thumbnails for images, chips for files */}
      {files.length > 0 && (
        <Box sx={{ px: 2, pb: 1, display: "flex", flexWrap: "wrap", gap: 0.75, alignItems: "center" }}>
          {files.map((f, i) => (
            f.isImage ? (
              <Box
                key={`${f.name}-${i}`}
                sx={{ position: "relative", width: 56, height: 56, borderRadius: 1, overflow: "hidden", border: 1, borderColor: "divider" }}
              >
                <Box component="img" src={f.dataUrl} alt={f.name}
                     sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                <IconButton
                  size="small"
                  onClick={() => removeFile(i)}
                  sx={{
                    position: "absolute", top: 0, right: 0,
                    width: 18, height: 18, p: 0,
                    bgcolor: "rgba(0,0,0,0.6)", color: "#fff",
                    "&:hover": { bgcolor: "rgba(0,0,0,0.8)" },
                  }}
                >
                  <Close sx={{ fontSize: 12 }} />
                </IconButton>
              </Box>
            ) : (
              <Chip
                key={`${f.name}-${i}`}
                icon={<AttachFile sx={{ fontSize: 16 }} />}
                label={`${f.name} · ${(f.size / 1024).toFixed(1)} KB`}
                onDelete={() => removeFile(i)}
                size="small"
                variant="outlined"
                sx={{ maxWidth: 260 }}
              />
            )
          ))}
        </Box>
      )}

      {/* Input area */}
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1, p: 2, borderTop: 1, borderColor: "divider" }}>
        <TextField
          fullWidth
          size="small"
          placeholder={t("chat.placeholder")}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          multiline
          maxRows={5}
          disabled={isLoading}
        />
        {showUpload && (
          <>
            <Tooltip title={project.type === "agent" ? t("chat.attachFiles") : t("chat.attachImage")}>
              <label htmlFor={`attach-${project.id}-${systemOverride ? "b" : "a"}`}>
                <Fab color="default" size="small" component="span">
                  <AttachFile fontSize="small" />
                </Fab>
              </label>
            </Tooltip>
            <HiddenInput
              onChange={handleAttachFiles}
              id={`attach-${project.id}-${systemOverride ? "b" : "a"}`}
              type="file"
              multiple={project.type === "agent"}
              accept={project.type === "agent" ? undefined : "image/*"}
            />
          </>
        )}
        <Tooltip title={t("chat.clear")}>
          <Fab color="default" size="small" onClick={handleClear}>
            <DeleteSweep fontSize="small" />
          </Fab>
        </Tooltip>
        {isLoading && streaming ? (
          <Tooltip title={t("chat.stop")}>
            <Fab color="error" size="small" onClick={handleStopStreaming}>
              <Stop fontSize="small" />
            </Fab>
          </Tooltip>
        ) : (
          <Fab
            color="primary"
            size="small"
            onClick={handleSend}
            disabled={isLoading || (!inputText.trim() && files.length === 0)}
          >
            <Send fontSize="small" />
          </Fab>
        )}
      </Box>
    </Box>
  );
}
