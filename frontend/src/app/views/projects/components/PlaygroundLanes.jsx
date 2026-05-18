import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import {
  Box, Chip, IconButton, Tooltip, Typography, styled,
} from "@mui/material";
import {
  Psychology, TerminalOutlined, ChatBubbleOutline,
  ContentCopy, Speed, Shield, Cached, CallSplit,
  AttachFile, CheckCircle, Loop, RadioButtonUnchecked,
  Person,
} from "@mui/icons-material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Terminal from "./Terminal";
import { FONT_MONO, pulse } from "app/components/page/pageStyles";

// Mirror of MessageBubble.splitThinking — keeps this file independent so
// the message-bubble rendering layer can change without us tracking it.
function splitThinking(text) {
  if (!text || typeof text !== "string") return { thoughts: [], answer: text || "", openThought: null };
  const thoughts = [];
  let answer = "";
  let openThought = null;
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf("<think>", i);
    if (open === -1) { answer += text.slice(i); break; }
    answer += text.slice(i, open);
    const close = text.indexOf("</think>", open + 7);
    if (close === -1) { openThought = text.slice(open + 7); break; }
    thoughts.push(text.slice(open + 7, close).trim());
    i = close + 8;
  }
  return { thoughts, answer, openThought };
}

// ───────────────────────────────────────────────────────────────────────
// Lane palette — one accent per channel. Picked so the playground reads
// as three distinct mental modes: cognition / action / deliverable.
const LANE_THEME = {
  thoughts: { accent: "#7c3aed", soft: "rgba(124,58,237,0.08)", label: "THOUGHTS", icon: Psychology },
  tools:    { accent: "#0891b2", soft: "rgba(8,145,178,0.08)",  label: "TOOLS",    icon: TerminalOutlined },
  output:   { accent: "#0f172a", soft: "rgba(15,23,42,0.05)",   label: "OUTPUT",   icon: ChatBubbleOutline },
};

const RAIL_WIDTH = 32;

// ── Rail: the vertical handle that lives on the LEFT edge of every
// lane. Clicking it collapses/expands the lane. Stays visible (28-32px
// wide) even when collapsed so the user has somewhere to click to
// re-open. Uses CSS writing-mode for the rotated label — feels more
// console-y than a rotated transform and stays readable at 11px.
const RailButton = styled("button", {
  shouldForwardProp: (p) => p !== "accent" && p !== "open" && p !== "active",
})(({ accent, open, active }) => ({
  position: "relative",
  flex: `0 0 ${RAIL_WIDTH}px`,
  width: RAIL_WIDTH,
  minWidth: RAIL_WIDTH,
  border: "none",
  borderRight: `1px solid rgba(15,23,42,0.06)`,
  background: open ? "#fff" : "#fafbfd",
  cursor: "pointer",
  padding: "10px 0 12px",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "space-between",
  fontFamily: FONT_MONO,
  fontSize: "0.66rem",
  letterSpacing: "0.32em",
  color: open ? accent : "rgba(15,23,42,0.45)",
  fontWeight: 700,
  transition: "background-color 0.18s ease, color 0.18s ease, box-shadow 0.18s ease",
  // Tactile accent stripe down the rail itself — only when open.
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, top: 0, bottom: 0,
    width: 3,
    background: open ? accent : "transparent",
    opacity: 0.9,
    transition: "background 0.18s ease",
  },
  // Live channel? Animate the stripe.
  "&::after": active ? {
    content: '""',
    position: "absolute",
    left: 0, top: 0, bottom: 0,
    width: 3,
    background: accent,
    animation: `${pulse} 1.6s ease-out infinite`,
  } : {},
  "&:hover": {
    background: open ? "#fff" : "#fff",
    color: accent,
    boxShadow: `inset -1px 0 0 ${accent}33`,
  },
}));

const RailLabel = styled("span")({
  writingMode: "vertical-rl",
  textOrientation: "mixed",
  transform: "rotate(180deg)",
  userSelect: "none",
});

const CountPill = styled("span", {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  fontFamily: FONT_MONO,
  fontSize: "0.6rem",
  letterSpacing: "0.05em",
  fontWeight: 700,
  color: "#fff",
  background: accent,
  borderRadius: 8,
  padding: "1px 6px",
  minWidth: 18,
  textAlign: "center",
}));

// ── Lane container — left rail + (when open) the header + scroll body.
function Lane({ id, count, isLive, open, onToggle, flex, autoScroll, children }) {
  const theme = LANE_THEME[id];
  const Icon = theme.icon;
  const bodyRef = useRef(null);

  // Two scroll behaviors, picked by the toolbar's auto-scroll switch:
  //   - on:  ALWAYS snap to bottom on render (mission-control mode,
  //          three live feeds racing).
  //   - off: stick only when the user was near the bottom already so
  //          scrolling up to read older entries isn't yanked back.
  const wasNearBottomRef = useRef(true);
  useEffect(() => {
    const el = bodyRef.current;
    if (!el || !open) return;
    if (autoScroll || wasNearBottomRef.current) el.scrollTop = el.scrollHeight;
  });
  const handleScroll = () => {
    const el = bodyRef.current;
    if (!el) return;
    const slack = 64;
    wasNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < slack;
  };

  return (
    <Box
      sx={{
        flex: open ? flex : `0 0 ${RAIL_WIDTH}px`,
        minWidth: open ? 240 : RAIL_WIDTH,
        display: "flex",
        flexDirection: "row",
        minHeight: 0,
        borderRight: "1px solid rgba(15,23,42,0.06)",
        background: "#fff",
        overflow: "hidden",
        transition: "flex 0.28s cubic-bezier(0.4, 0, 0.2, 1), min-width 0.28s cubic-bezier(0.4, 0, 0.2, 1)",
      }}
    >
      <RailButton
        accent={theme.accent}
        open={open}
        active={isLive}
        onClick={onToggle}
        title={open ? `Collapse ${theme.label.toLowerCase()}` : `Expand ${theme.label.toLowerCase()}`}
      >
        <Icon sx={{ fontSize: 14, color: open ? theme.accent : "inherit" }} />
        <RailLabel>{theme.label}</RailLabel>
        {count > 0 && <CountPill accent={theme.accent}>{count > 999 ? "999+" : count}</CountPill>}
      </RailButton>

      {open && (
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", minWidth: 0, minHeight: 0 }}>
          {/* Header strip — count + live dot */}
          <Box
            sx={{
              flexShrink: 0,
              display: "flex",
              alignItems: "center",
              gap: 1,
              px: 1.5, py: 1,
              borderBottom: "1px solid rgba(15,23,42,0.06)",
              background: theme.soft,
            }}
          >
            <Typography
              sx={{
                fontFamily: FONT_MONO, fontSize: "0.66rem",
                letterSpacing: "0.16em", fontWeight: 800,
                color: theme.accent,
              }}
            >
              {theme.label}
            </Typography>
            <Typography
              sx={{
                fontFamily: FONT_MONO, fontSize: "0.66rem",
                color: "rgba(15,23,42,0.5)", fontWeight: 600,
              }}
            >
              {count}
            </Typography>
            {isLive && (
              <Box
                sx={{
                  width: 6, height: 6, borderRadius: "50%",
                  background: theme.accent,
                  boxShadow: `0 0 6px ${theme.accent}`,
                  animation: `${pulse} 1.6s ease-out infinite`,
                  ml: "auto",
                }}
              />
            )}
          </Box>
          <Box
            ref={bodyRef}
            onScroll={handleScroll}
            sx={{ flex: 1, overflow: "auto", minHeight: 0 }}
          >
            {children}
          </Box>
        </Box>
      )}
    </Box>
  );
}

// ── Tag for the per-item turn marker (T1 · 14:32 etc).
const TurnTag = styled("span", {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  fontFamily: FONT_MONO,
  fontSize: "0.62rem",
  letterSpacing: "0.08em",
  fontWeight: 700,
  color: accent,
  textTransform: "uppercase",
}));

// ───────────────────────────────────────────────────────────────────────
// Lane content renderers

function ThoughtsLaneItem({ entry, accent, idx }) {
  const isLive = !!entry.isLive;
  return (
    <Box
      sx={{
        px: 1.5, py: 1.25,
        borderBottom: "1px solid rgba(15,23,42,0.04)",
        position: "relative",
        ...(isLive && {
          background: "rgba(124,58,237,0.04)",
          "&::before": {
            content: '""',
            position: "absolute",
            left: 0, top: 0, bottom: 0, width: 2,
            background: accent,
            animation: `${pulse} 1.4s ease-out infinite`,
          },
        }),
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
        <TurnTag accent={accent}>T{entry.turnIdx + 1}</TurnTag>
        <Box sx={{ flex: 1, height: 1, background: "rgba(15,23,42,0.06)" }} />
        {isLive && (
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.58rem",
            letterSpacing: "0.16em", fontWeight: 700,
            color: accent,
          }}>
            LIVE
          </Typography>
        )}
      </Box>
      <Typography
        sx={{
          fontSize: "0.84rem",
          fontStyle: "italic",
          color: "text.secondary",
          whiteSpace: "pre-wrap",
          lineHeight: 1.55,
        }}
      >
        {entry.text}
      </Typography>
    </Box>
  );
}

function ToolsLaneItem({ entry, accent }) {
  const isLive = entry.status === "running";
  const isError = entry.status === "error";
  const statusIcon = isLive
    ? <Loop sx={{ fontSize: 14, color: accent, animation: "spin 2s linear infinite", "@keyframes spin": { "100%": { transform: "rotate(360deg)" } } }} />
    : isError
      ? <RadioButtonUnchecked sx={{ fontSize: 14, color: "#dc2626" }} />
      : <CheckCircle sx={{ fontSize: 14, color: "#16a34a" }} />;

  // Render the actual tool I/O via the existing Terminal component so
  // styles stay identical to the current playground panel.
  const terminalMessage = {
    reasoning: {
      steps: [{
        actions: [{
          action: entry.name || "tool",
          input: (() => {
            if (entry.args == null) return null;
            if (typeof entry.args === "object") return entry.args;
            try { const p = JSON.parse(entry.args); return p; } catch { return { args: entry.args }; }
          })(),
          output: isLive ? "…running…" : (entry.output || "(no output)"),
        }],
      }],
    },
  };

  return (
    <Box
      sx={{
        px: 1, py: 1,
        borderBottom: "1px solid rgba(15,23,42,0.04)",
        position: "relative",
        ...(isLive && {
          background: "rgba(8,145,178,0.04)",
          "&::before": {
            content: '""',
            position: "absolute",
            left: 0, top: 0, bottom: 0, width: 2,
            background: accent,
            animation: `${pulse} 1.4s ease-out infinite`,
          },
        }),
        ...(isError && {
          background: "rgba(220,38,38,0.04)",
        }),
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 0.5 }}>
        {statusIcon}
        <TurnTag accent={accent}>T{entry.turnIdx + 1}</TurnTag>
        <Typography sx={{
          fontFamily: FONT_MONO, fontSize: "0.74rem",
          fontWeight: 700, color: "#0f172a",
        }}>
          {entry.name || "tool"}
        </Typography>
        {entry.latency_ms != null && (
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.62rem",
            color: "rgba(15,23,42,0.5)", ml: "auto",
          }}>
            {entry.latency_ms > 1000 ? `${(entry.latency_ms / 1000).toFixed(1)}s` : `${entry.latency_ms}ms`}
          </Typography>
        )}
      </Box>
      <Box sx={{ "& > div": { margin: "0 !important", borderRadius: "4px !important" } }}>
        <Terminal message={terminalMessage} />
      </Box>
    </Box>
  );
}

// Tiny reusable styles inside the Output lane — keeps user/assistant
// turns visually distinct without going full bubble (lanes already give
// us the visual containment).
function OutputLaneItem({ entry, accent, onBranch, onCopy, copied, isLast }) {
  if (entry.role === "user") {
    const meta = entry.meta;
    return (
      <Box sx={{ px: 1.5, py: 1.25, borderBottom: "1px solid rgba(15,23,42,0.04)" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5, flexWrap: "wrap" }}>
          <Person sx={{ fontSize: 13, color: accent }} />
          <TurnTag accent={accent}>T{entry.turnIdx + 1} · USER</TurnTag>
          {meta && meta.user_id != null && (
            <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.6rem", color: "rgba(15,23,42,0.5)" }}>
              #{meta.user_id}
            </Typography>
          )}
          {meta && meta.date && (
            <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.6rem", color: "rgba(15,23,42,0.5)", ml: "auto" }}>
              {new Date(meta.date).toLocaleString()}
            </Typography>
          )}
        </Box>
        {entry.image && (
          <Box component="img" src={entry.image}
            sx={{ maxWidth: "100%", maxHeight: 160, borderRadius: 1, mb: 0.5, display: "block" }} />
        )}
        {entry.files && entry.files.length > 0 && (
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: 0.5 }}>
            {entry.files.map((f, i) =>
              f.isImage && f.dataUrl ? (
                <Box key={i} component="img" src={f.dataUrl} alt={f.name}
                  sx={{ maxWidth: 120, maxHeight: 120, borderRadius: 0.5, display: "block" }} />
              ) : (
                <Chip key={i} icon={<AttachFile sx={{ fontSize: 13 }} />}
                  label={f.size ? `${f.name} · ${(f.size / 1024).toFixed(1)} KB` : f.name}
                  size="small" variant="outlined" sx={{ height: 22, fontSize: "0.7rem" }} />
              )
            )}
          </Box>
        )}
        {entry.text && (
          <Typography sx={{
            fontSize: "0.88rem",
            whiteSpace: "pre-wrap",
            color: "#0f172a",
            fontWeight: 500,
          }}>
            {entry.text}
          </Typography>
        )}
      </Box>
    );
  }

  // assistant
  const pending = entry.pending;
  const hasContent = entry.text && entry.text.trim().length > 0;
  return (
    <Box
      sx={{
        px: 1.5, py: 1.25,
        borderBottom: isLast ? "none" : "1px solid rgba(15,23,42,0.04)",
        position: "relative",
        ...(entry.isLive && {
          "&::before": {
            content: '""',
            position: "absolute",
            left: 0, top: 0, bottom: 0, width: 2,
            background: accent,
            animation: `${pulse} 1.6s ease-out infinite`,
          },
        }),
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.5, flexWrap: "wrap" }}>
        <TurnTag accent={accent}>T{entry.turnIdx + 1} · ASST</TurnTag>
        {entry.isLive && (
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.58rem",
            letterSpacing: "0.16em", fontWeight: 700,
            color: accent,
          }}>
            STREAMING
          </Typography>
        )}
        {entry.meta && entry.meta.llm && (
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.6rem",
            color: "#1e3a8a", fontWeight: 700, letterSpacing: "0.04em",
          }}>
            {entry.meta.llm}
          </Typography>
        )}
        {entry.meta && entry.meta.status && entry.meta.status !== "success" && (
          <Chip
            size="small"
            label={entry.meta.status}
            sx={{
              height: 16, fontSize: "0.58rem", fontFamily: FONT_MONO, fontWeight: 700,
              background: "rgba(239,68,68,0.12)", color: "#b91c1c",
            }}
          />
        )}
        <Box sx={{ flex: 1 }} />
        {!pending && hasContent && (
          <Tooltip title={copied ? "Copied!" : "Copy"}>
            <IconButton size="small" onClick={() => onCopy(entry.text)} sx={{ p: 0.25 }}>
              <ContentCopy sx={{ fontSize: 13 }} />
            </IconButton>
          </Tooltip>
        )}
        {!pending && onBranch && (
          <Tooltip title="Branch conversation here">
            <IconButton size="small" onClick={() => onBranch(entry.turnIdx)} sx={{ p: 0.25 }}>
              <CallSplit sx={{ fontSize: 13 }} />
            </IconButton>
          </Tooltip>
        )}
      </Box>

      {/* Plan checklist if the auto-planner ran on this turn */}
      {Array.isArray(entry.plan) && entry.plan.length > 0 && (() => {
        const stepStates = Array.isArray(entry.stepSummaries) ? entry.stepSummaries : [];
        const isStreamingShape = stepStates.length > 0 && "status" in stepStates[0];
        const rows = isStreamingShape
          ? stepStates
          : [
              ...entry.plan.map((name, i) => ({ name, status: "done", summary: stepStates[i]?.result || "" })),
              { name: "Synthesize final answer", status: "done", synthetic: true },
            ];
        const done = rows.filter((r) => r.status === "done").length;
        return (
          <Box sx={{
            mb: 1, px: 1, py: 0.75,
            border: "1px solid rgba(15,23,42,0.08)",
            borderRadius: 0.75,
            background: "rgba(15,23,42,0.02)",
          }}>
            <Typography sx={{
              fontFamily: FONT_MONO, fontSize: "0.6rem",
              letterSpacing: "0.16em", fontWeight: 700,
              color: "rgba(15,23,42,0.55)", mb: 0.5,
            }}>
              PLAN · {done}/{rows.length}
            </Typography>
            {rows.map((step, i) => (
              <Box key={i} sx={{
                display: "flex", alignItems: "flex-start", gap: 0.5,
                py: 0.25, fontSize: "0.78rem",
                opacity: step.status === "pending" ? 0.55 : 1,
              }}>
                <Box sx={{ display: "flex", alignItems: "center", pt: "2px" }}>
                  {step.status === "done"
                    ? <CheckCircle sx={{ fontSize: 12, color: "#16a34a" }} />
                    : step.status === "running"
                      ? <Loop sx={{ fontSize: 12, color: accent, animation: "spin 2s linear infinite", "@keyframes spin": { "100%": { transform: "rotate(360deg)" } } }} />
                      : <RadioButtonUnchecked sx={{ fontSize: 12, color: "rgba(15,23,42,0.35)" }} />}
                </Box>
                <Typography sx={{ fontSize: "0.78rem", fontWeight: step.status === "running" ? 600 : 400 }}>
                  {step.name}
                </Typography>
              </Box>
            ))}
          </Box>
        );
      })()}

      {pending && !hasContent ? (
        <Typography sx={{ fontSize: "0.85rem", color: "text.secondary", fontStyle: "italic" }}>
          Thinking…
        </Typography>
      ) : (
        <Box sx={{
          fontSize: "0.9rem",
          color: "#0f172a",
          "& p": { margin: "0.3em 0" },
          "& pre": {
            background: "rgba(15,23,42,0.05)", padding: "8px", borderRadius: 4,
            fontSize: "0.78rem", overflowX: "auto",
          },
          "& code": { fontFamily: FONT_MONO, fontSize: "0.82rem" },
          "& table": { borderCollapse: "collapse", width: "100%", margin: "8px 0", fontSize: "0.82rem" },
          "& th, & td": { border: "1px solid rgba(15,23,42,0.1)", padding: "6px 10px", textAlign: "left" },
          "& th": { background: "rgba(15,23,42,0.04)", fontWeight: 600 },
        }}>
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              img: ({ node, ...props }) => (
                <Box component="img" {...props} sx={{
                  display: "block", maxWidth: "100%", maxHeight: 380,
                  height: "auto", borderRadius: 1, my: 1,
                }} />
              ),
            }}
          >
            {entry.text || ""}
          </ReactMarkdown>
        </Box>
      )}

      {entry.sources && entry.sources.length > 0 && (
        <Box sx={{ mt: 1 }}>
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.6rem",
            letterSpacing: "0.16em", fontWeight: 700,
            color: "rgba(15,23,42,0.55)", mb: 0.5,
          }}>
            SOURCES · {entry.sources.length}
          </Typography>
          {entry.sources.map((src, i) => (
            <Box key={i} sx={{
              mb: 0.5, p: 0.75, borderRadius: 0.75,
              background: "rgba(15,23,42,0.03)",
            }}>
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", fontWeight: 700, color: accent }}>
                {src.source || `Source ${i + 1}`}
                {src.score !== undefined && ` · ${(src.score * 100).toFixed(0)}%`}
              </Typography>
              <Typography sx={{ fontSize: "0.78rem", color: "text.secondary", whiteSpace: "pre-wrap" }}>
                {typeof src === "string" ? src : (src.text || "")}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {entry.metadata && !pending && (
        <Box sx={{ display: "flex", gap: 0.5, mt: 0.75, flexWrap: "wrap" }}>
          {entry.metadata.guard && <Chip icon={<Shield />} label="Guard" size="small" color="warning" variant="outlined" sx={{ height: 20, fontSize: "0.68rem" }} />}
          {entry.metadata.cached && <Chip icon={<Cached />} label="Cached" size="small" color="info" variant="outlined" sx={{ height: 20, fontSize: "0.68rem" }} />}
          {entry.metadata.tokens && (entry.metadata.tokens.input > 0 || entry.metadata.tokens.output > 0) && (
            <Chip label={`${entry.metadata.tokens.input + entry.metadata.tokens.output} tok`}
              size="small" variant="outlined" sx={{ height: 20, fontSize: "0.68rem" }} />
          )}
          {entry.metadata.latency_ms > 0 && (
            <Chip icon={<Speed />}
              label={entry.metadata.latency_ms > 1000 ? `${(entry.metadata.latency_ms / 1000).toFixed(1)}s` : `${entry.metadata.latency_ms}ms`}
              size="small" variant="outlined" sx={{ height: 20, fontSize: "0.68rem" }} />
          )}
        </Box>
      )}

      {/* Replay-only error block — shows the raw error text from the
          OutputDatabase row when the turn status wasn't success.
          Hidden in live playground because errors there land as bubble
          messages already. */}
      {entry.meta && entry.meta.status && entry.meta.status !== "success" && entry.meta.error && (
        <Box sx={{
          mt: 0.75, p: 1,
          borderRadius: 0.75,
          border: "1px solid rgba(239,68,68,0.25)",
          background: "rgba(239,68,68,0.04)",
          fontFamily: FONT_MONO, fontSize: "0.72rem",
          color: "#9f3a38", whiteSpace: "pre-wrap",
        }}>
          {entry.meta.error}
        </Box>
      )}
    </Box>
  );
}

// ───────────────────────────────────────────────────────────────────────
// Derive — extract Thoughts/Tools/Output streams from messages + live state.

function deriveLanes(messages, streamingText, streamingPlan, streamingToolCalls) {
  const thoughts = [];
  const tools = [];
  const output = [];
  const dedupeThoughts = new Set();

  messages.forEach((msg, turnIdx) => {
    if (msg.question || (msg._files && msg._files.length) || msg._image) {
      output.push({
        role: "user",
        turnIdx,
        text: msg.question || "",
        files: msg._files,
        image: msg._image,
        meta: msg._meta || null,
      });
    }

    if (msg.answer === null || msg.answer === undefined) {
      if (msg.answer === null) {
        output.push({ role: "assistant", turnIdx, text: null, pending: true });
      }
      return;
    }

    const { thoughts: extracted, answer: answerText, openThought } = splitThinking(msg.answer);
    extracted.forEach((t) => {
      const key = `${turnIdx}::${t}`;
      if (t && !dedupeThoughts.has(key)) {
        dedupeThoughts.add(key);
        thoughts.push({ turnIdx, text: t, isLive: false });
      }
    });
    if (openThought && openThought.trim()) {
      thoughts.push({ turnIdx, text: openThought, isLive: true });
    }

    const reasoningSteps = (msg.reasoning && msg.reasoning.steps) || [];
    reasoningSteps.forEach((step) => {
      (step.actions || []).forEach((a) => {
        if (a.action === "reasoning") {
          const txt = a.output;
          const key = `${turnIdx}::${txt}`;
          if (txt && !dedupeThoughts.has(key)) {
            dedupeThoughts.add(key);
            thoughts.push({ turnIdx, text: txt, isLive: false });
          }
        } else {
          tools.push({
            turnIdx,
            name: a.action,
            args: a.input,
            output: a.output,
            status: "done",
          });
        }
      });
    });

    (msg.live_tool_calls || []).forEach((call) => {
      tools.push({
        turnIdx,
        name: call.tool,
        args: call.args,
        output: call.output || call.error || "",
        status: call.status,
        latency_ms: call.latency_ms,
      });
    });

    output.push({
      role: "assistant",
      turnIdx,
      text: answerText,
      sources: msg.sources,
      plan: msg.plan,
      stepSummaries: msg.step_summaries,
      meta: msg._meta || null,
      metadata: {
        latency_ms: msg.latency_ms, tokens: msg.tokens,
        cached: msg.cached, guard: msg.guard, id: msg.id,
      },
    });
  });

  // Streaming bubble — extra in-flight turn that lives on top of the
  // last placeholder until the final SSE event lands.
  const hasStream = !!(streamingText || streamingPlan || (streamingToolCalls && streamingToolCalls.length > 0));
  if (hasStream) {
    const liveTurnIdx = Math.max(messages.length - 1, 0);
    const { thoughts: liveT, answer: liveA, openThought: liveOpen } = splitThinking(streamingText || "");

    liveT.forEach((t) => {
      const key = `live::${liveTurnIdx}::${t}`;
      if (t && !dedupeThoughts.has(key)) {
        dedupeThoughts.add(key);
        thoughts.push({ turnIdx: liveTurnIdx, text: t, isLive: false });
      }
    });
    if (liveOpen && liveOpen.trim()) {
      thoughts.push({ turnIdx: liveTurnIdx, text: liveOpen, isLive: true });
    }

    (streamingToolCalls || []).forEach((call) => {
      tools.push({
        turnIdx: liveTurnIdx,
        name: call.tool,
        args: call.args,
        output: call.output || call.error || "",
        status: call.status,
        latency_ms: call.latency_ms,
      });
    });

    // Replace the last placeholder assistant entry (if any) with the
    // streaming text — avoids "Thinking…" duplicating beside live text.
    const lastOut = output[output.length - 1];
    if (lastOut && lastOut.role === "assistant" && lastOut.pending) {
      output[output.length - 1] = {
        ...lastOut,
        pending: false,
        isLive: true,
        text: liveA,
        plan: streamingPlan?.plan,
        stepSummaries: streamingPlan?.steps,
      };
    } else if (liveA || streamingPlan) {
      output.push({
        role: "assistant",
        turnIdx: liveTurnIdx,
        text: liveA,
        plan: streamingPlan?.plan,
        stepSummaries: streamingPlan?.steps,
        isLive: true,
      });
    }
  }

  return {
    thoughts, tools, output,
    isLive: { thoughts: thoughts.some((t) => t.isLive), tools: tools.some((t) => t.status === "running"), output: output.some((o) => o.isLive) },
  };
}

// ───────────────────────────────────────────────────────────────────────
// Public

// Start state: only the Output lane is visible. Thoughts / Tools rails
// remain visible (28-32px) so the user can manually expand any time;
// they also auto-expand once on first content (handled below).
const INITIAL_OPEN = { thoughts: false, tools: false, output: true };

export default function PlaygroundLanes({
  messages,
  streamingText,
  streamingPlan,
  streamingToolCalls,
  chatMode,
  onBranch,
  autoScroll = true,
  // Playground wants Thoughts/Tools to pop open the first time content
  // arrives. Replay doesn't — the conversation is already over, so it
  // opens in Output-only mode and waits for the user to peek at the
  // other lanes if they care.
  autoExpand = true,
}) {
  const [open, setOpen] = useState(INITIAL_OPEN);
  // One-shot auto-expand: when content first appears in a lane, pop it
  // open. After that, leave it strictly under user control — once
  // they've collapsed a noisy lane they shouldn't get fought every
  // turn.
  const [autoExpandedOnce, setAutoExpandedOnce] = useState({ thoughts: false, tools: false });
  const [copiedKey, setCopiedKey] = useState(null);

  // Don't allow collapsing all three at once — leave at least one open
  // so there's somewhere to look. The rail of any closed lane stays
  // clickable so the user can re-open it.
  const toggle = useCallback((lane) => {
    setOpen((cur) => {
      const next = { ...cur, [lane]: !cur[lane] };
      if (!next.thoughts && !next.tools && !next.output) {
        return cur;
      }
      return next;
    });
    // Treat any manual toggle as "user has taken over" — flag the lane
    // as already auto-expanded so we don't re-pop it on the next thought.
    if (lane === "thoughts" || lane === "tools") {
      setAutoExpandedOnce((cur) => ({ ...cur, [lane]: true }));
    }
  }, []);

  const lanes = useMemo(
    () => deriveLanes(messages, streamingText, streamingPlan, streamingToolCalls),
    [messages, streamingText, streamingPlan, streamingToolCalls],
  );

  // First-content auto-expand for Thoughts. Skipped when autoExpand is
  // false (replay) so the dialog opens Output-only no matter how much
  // thinking the agent did in the past.
  useEffect(() => {
    if (!autoExpand) return;
    if (!autoExpandedOnce.thoughts && lanes.thoughts.length > 0) {
      setOpen((cur) => ({ ...cur, thoughts: true }));
      setAutoExpandedOnce((cur) => ({ ...cur, thoughts: true }));
    }
  }, [lanes.thoughts.length, autoExpandedOnce.thoughts, autoExpand]);

  // First-content auto-expand for Tools.
  useEffect(() => {
    if (!autoExpand) return;
    if (!autoExpandedOnce.tools && lanes.tools.length > 0) {
      setOpen((cur) => ({ ...cur, tools: true }));
      setAutoExpandedOnce((cur) => ({ ...cur, tools: true }));
    }
  }, [lanes.tools.length, autoExpandedOnce.tools, autoExpand]);

  // Reset on session clear so the next fresh chat gets the same initial
  // experience (Output-only, Thoughts/Tools pop open once when used).
  useEffect(() => {
    if (messages.length === 0) {
      setOpen(INITIAL_OPEN);
      setAutoExpandedOnce({ thoughts: false, tools: false });
    }
  }, [messages.length]);

  const handleCopy = (text) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    const key = `${Date.now()}`;
    setCopiedKey(key);
    setTimeout(() => setCopiedKey((c) => (c === key ? null : c)), 1500);
  };

  return (
    <Box
      sx={{
        flex: 1,
        display: "flex",
        flexDirection: "row",
        minHeight: 0,
        background: "#fafbfd",
      }}
    >
      <Lane
        id="thoughts"
        count={lanes.thoughts.length}
        isLive={lanes.isLive.thoughts}
        open={open.thoughts}
        onToggle={() => toggle("thoughts")}
        flex={1.05}
        autoScroll={autoScroll}
      >
        {lanes.thoughts.length === 0 ? (
          <EmptyState label="No thoughts captured yet" />
        ) : (
          lanes.thoughts.map((entry, i) => (
            <ThoughtsLaneItem key={i} entry={entry} accent={LANE_THEME.thoughts.accent} idx={i} />
          ))
        )}
      </Lane>

      <Lane
        id="tools"
        count={lanes.tools.length}
        isLive={lanes.isLive.tools}
        open={open.tools}
        onToggle={() => toggle("tools")}
        flex={1.25}
        autoScroll={autoScroll}
      >
        {lanes.tools.length === 0 ? (
          <EmptyState label="No tool calls yet" />
        ) : (
          lanes.tools.map((entry, i) => (
            <ToolsLaneItem key={i} entry={entry} accent={LANE_THEME.tools.accent} />
          ))
        )}
      </Lane>

      <Lane
        id="output"
        count={lanes.output.length}
        isLive={lanes.isLive.output}
        open={open.output}
        onToggle={() => toggle("output")}
        flex={1.4}
        autoScroll={autoScroll}
      >
        {lanes.output.length === 0 ? (
          <EmptyState label="No turns yet — send a message below" />
        ) : (
          lanes.output.map((entry, i) => (
            <OutputLaneItem
              key={i}
              entry={entry}
              accent={LANE_THEME.output.accent}
              onBranch={chatMode && entry.role === "assistant" && entry.text && !entry.isLive ? onBranch : null}
              onCopy={handleCopy}
              copied={!!copiedKey}
              isLast={i === lanes.output.length - 1}
            />
          ))
        )}
      </Lane>
    </Box>
  );
}

function EmptyState({ label }) {
  return (
    <Box sx={{
      display: "flex", alignItems: "center", justifyContent: "center",
      height: "100%", minHeight: 120,
      px: 2, textAlign: "center",
    }}>
      <Typography sx={{
        fontFamily: FONT_MONO, fontSize: "0.68rem",
        letterSpacing: "0.16em", fontWeight: 600,
        color: "rgba(15,23,42,0.35)", textTransform: "uppercase",
      }}>
        {label}
      </Typography>
    </Box>
  );
}
