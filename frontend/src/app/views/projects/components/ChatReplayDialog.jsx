import React, { useEffect, useMemo, useState } from "react";
import {
  Alert, AppBar, Box, Chip, CircularProgress, Dialog, IconButton,
  Slide, Toolbar, Tooltip, Typography,
} from "@mui/material";
import { Close, ContentCopy, ExpandMore, ExpandLess } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO } from "app/components/page/pageStyles";
import PlaygroundLanes from "./PlaygroundLanes";

const Transition = React.forwardRef(function Transition(props, ref) {
  return <Slide direction="up" ref={ref} {...props} />;
});

const safeJson = (s) => {
  if (!s) return null;
  if (typeof s !== "string") return s;
  try { return JSON.parse(s); } catch { return null; }
};

// OutputDatabase row → MessageBubble message-shape. tool_trace becomes
// the same `reasoning.steps[].actions[]` shape that live_tool_calls
// produces — PlaygroundLanes pulls thoughts/tools out of this same
// reasoning structure.
function turnToMessage(turn) {
  const traceEntries = safeJson(turn.tool_trace) || [];
  const reasoning = traceEntries.length
    ? {
        steps: [{
          actions: traceEntries.map((c) => ({
            action: c.tool || "tool",
            input: c.args || "",
            output: c.status === "error"
              ? (c.error || "(error)")
              : (c.status === "running" ? "…running…" : (c.output || c.error || "ok")),
          })),
        }],
      }
    : null;

  const ctx = safeJson(turn.context);
  const sources = Array.isArray(ctx)
    ? ctx.map((c) => ({
        source: c.source || c.metadata?.source || "—",
        text: c.text || c.page_content || "",
        score: c.score,
      }))
    : null;

  const attachments = safeJson(turn.attachments) || [];
  const _files = attachments.map((a) => ({
    name: a.name,
    size: a.size,
    mime_type: a.mime_type,
    isImage: (a.mime_type || "").startsWith("image/"),
    dataUrl: a.dataUrl || null,
  }));

  const _image = turn.image
    ? (turn.image.startsWith("data:") ? turn.image : `data:image/png;base64,${turn.image}`)
    : null;

  return {
    question: turn.question,
    answer: turn.answer,
    id: turn.chat_id,
    latency_ms: turn.latency_ms,
    tokens: { input: turn.input_tokens || 0, output: turn.output_tokens || 0 },
    sources,
    reasoning,
    _files,
    _image,
    _meta: {
      date: turn.date,
      llm: turn.llm,
      status: turn.status,
      error: turn.error,
      user_id: turn.user_id,
    },
  };
}

function shortChatId(id) {
  if (!id) return "";
  return id.length > 12 ? `${id.slice(0, 4)}…${id.slice(-4)}` : id;
}

export default function ChatReplayDialog({ open, onClose, projectId, projectName, chatId }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [loading, setLoading] = useState(false);
  const [turns, setTurns] = useState([]);
  const [truncated, setTruncated] = useState(false);
  const [error, setError] = useState(null);
  const [copiedId, setCopiedId] = useState(false);
  // System-prompt drawer — collapsed by default since the lanes are
  // the main act in a replay; users can pop it open if they need to
  // see what guidance the assistant was running under.
  const [showSystem, setShowSystem] = useState(false);

  useEffect(() => {
    if (!open || !projectId || !chatId) return;
    setLoading(true);
    setError(null);
    setTurns([]);
    setTruncated(false);
    setShowSystem(false);
    api.get(`/projects/${projectId}/logs/conversation/${encodeURIComponent(chatId)}`, auth.user.token)
      .then((d) => {
        setTurns(Array.isArray(d.turns) ? d.turns : []);
        setTruncated(!!d.truncated);
      })
      .catch(() => setError(t("projects.logs.replay.loadError", "Failed to load conversation.")))
      .finally(() => setLoading(false));
  }, [open, projectId, chatId, auth.user.token, t]);

  const messages = useMemo(() => turns.map(turnToMessage), [turns]);
  const systemPrompt = turns[0]?.system_prompt || "";

  const handleCopyId = () => {
    if (!chatId) return;
    navigator.clipboard.writeText(chatId);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 1500);
  };

  return (
    <Dialog
      fullScreen
      open={open}
      onClose={onClose}
      TransitionComponent={Transition}
      PaperProps={{ sx: { backgroundColor: "#f7f8fb", display: "flex", flexDirection: "column" } }}
    >
      <AppBar position="static" elevation={0} sx={{
        background: "linear-gradient(135deg, #0f172a 0%, #1e3a8a 100%)",
        borderBottom: "1px solid rgba(255,255,255,0.08)",
        flexShrink: 0,
      }}>
        <Toolbar sx={{ gap: 1.5 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="h6" sx={{ color: "#fff", fontWeight: 600, lineHeight: 1.2 }}>
              {t("projects.logs.replay.title", "Conversation")}
            </Typography>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.25, flexWrap: "wrap" }}>
              <Box
                component="span"
                sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem", color: "rgba(255,255,255,0.75)" }}
              >
                {projectName} · chat_id {shortChatId(chatId)}
              </Box>
              <Tooltip title={copiedId ? "Copied" : chatId} arrow>
                <IconButton size="small" onClick={handleCopyId} sx={{ color: "rgba(255,255,255,0.7)" }}>
                  <ContentCopy sx={{ fontSize: 14 }} />
                </IconButton>
              </Tooltip>
              {turns.length > 0 && (
                <Chip
                  size="small"
                  label={t("projects.logs.replay.turnCount", { count: turns.length, defaultValue: "{{count}} turns" })}
                  sx={{
                    height: 20, fontSize: "0.68rem", fontFamily: FONT_MONO,
                    backgroundColor: "rgba(255,255,255,0.12)", color: "#fff",
                  }}
                />
              )}
              {systemPrompt && (
                <Tooltip title={showSystem ? "Hide system prompt" : "Show system prompt"}>
                  <Chip
                    size="small"
                    icon={showSystem
                      ? <ExpandLess sx={{ fontSize: 14, color: "#fff !important" }} />
                      : <ExpandMore sx={{ fontSize: 14, color: "#fff !important" }} />}
                    label="SYSTEM PROMPT"
                    onClick={() => setShowSystem((s) => !s)}
                    sx={{
                      height: 20, fontSize: "0.6rem", fontFamily: FONT_MONO,
                      letterSpacing: "0.12em", fontWeight: 700,
                      backgroundColor: "rgba(255,255,255,0.12)", color: "#fff",
                      cursor: "pointer",
                      "&:hover": { backgroundColor: "rgba(255,255,255,0.2)" },
                    }}
                  />
                </Tooltip>
              )}
            </Box>
          </Box>
          <IconButton onClick={onClose} sx={{ color: "#fff" }}>
            <Close />
          </IconButton>
        </Toolbar>
      </AppBar>

      {/* Optional system-prompt drawer, collapsed by default. */}
      {systemPrompt && showSystem && (
        <Box sx={{
          flexShrink: 0,
          mx: { xs: 2, md: 4 }, mt: 2,
          p: 2,
          borderRadius: 2,
          border: "1px solid rgba(15,23,42,0.08)",
          backgroundColor: "#fff",
        }}>
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.62rem",
            letterSpacing: "0.18em", fontWeight: 700,
            color: "text.disabled", mb: 0.75,
          }}>
            SYSTEM PROMPT
          </Typography>
          <Box sx={{
            whiteSpace: "pre-wrap",
            fontSize: "0.85rem",
            color: "text.secondary",
            maxHeight: 220, overflow: "auto",
          }}>
            {systemPrompt}
          </Box>
        </Box>
      )}

      {truncated && (
        <Alert severity="warning" sx={{ flexShrink: 0, mx: { xs: 2, md: 4 }, mt: 2 }}>
          {t("projects.logs.replay.truncated", "Showing first 500 turns of this conversation.")}
        </Alert>
      )}
      {error && (
        <Alert severity="error" sx={{ flexShrink: 0, mx: { xs: 2, md: 4 }, mt: 2 }}>{error}</Alert>
      )}

      {loading && (
        <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <CircularProgress />
        </Box>
      )}

      {!loading && !error && messages.length === 0 && (
        <Box sx={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", color: "text.disabled" }}>
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.78rem",
            letterSpacing: "0.16em", textTransform: "uppercase",
          }}>
            {t("projects.logs.replay.empty", "No turns found for this chat.")}
          </Typography>
        </Box>
      )}

      {!loading && !error && messages.length > 0 && (
        <Box sx={{
          flex: 1, minHeight: 0,
          display: "flex",
          mx: { xs: 1, md: 2 },
          my: 2,
          borderRadius: 2,
          overflow: "hidden",
          border: "1px solid rgba(15,23,42,0.08)",
          background: "#fff",
        }}>
          <PlaygroundLanes
            messages={messages}
            streamingText=""
            streamingPlan={null}
            streamingToolCalls={[]}
            chatMode={false}
            onBranch={undefined}
            autoScroll={false}
            autoExpand={false}
          />
        </Box>
      )}
    </Dialog>
  );
}
