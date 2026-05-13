import { useState } from "react";
import {
  Box, Chip, Collapse, IconButton, Typography, styled, Tooltip,
  Accordion, AccordionSummary, AccordionDetails,
} from "@mui/material";
import { ContentCopy, ExpandMore, Shield, Cached, Speed, TerminalOutlined, CallSplit, AttachFile, Psychology, CheckCircle, RadioButtonUnchecked, Loop } from "@mui/icons-material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Terminal from "./Terminal";

// Pull `<think>...</think>` blocks out of a streaming or final answer
// so we can render them in a separate dim panel (like `ollama run` does).
//
// During streaming we may see `<think>` opened but `</think>` not yet
// arrived — `openThought` carries that partial chunk so the UI can show
// "thinking…" content live and replace it with a closed segment once
// `</think>` lands.
function splitThinking(text) {
  if (!text || typeof text !== "string") {
    return { thoughts: [], answer: text || "", openThought: null };
  }
  const thoughts = [];
  let answer = "";
  let openThought = null;
  let i = 0;
  while (i < text.length) {
    const open = text.indexOf("<think>", i);
    if (open === -1) {
      answer += text.slice(i);
      break;
    }
    answer += text.slice(i, open);
    const close = text.indexOf("</think>", open + 7);
    if (close === -1) {
      // Unterminated — streaming partial. Treat the rest as live thought.
      openThought = text.slice(open + 7);
      break;
    }
    thoughts.push(text.slice(open + 7, close).trim());
    i = close + 8;
  }
  return { thoughts, answer, openThought };
}

const QuestionBubble = styled(Box)(({ theme }) => ({
  backgroundColor: theme.palette.primary.main,
  color: "#fff",
  padding: "10px 16px",
  borderRadius: "16px 16px 4px 16px",
  maxWidth: "80%",
  marginLeft: "auto",
  wordBreak: "break-word",
  whiteSpace: "pre-wrap",
}));

const AnswerBubble = styled(Box)(({ theme }) => ({
  backgroundColor: theme.palette.mode === "dark" ? "#2d2d2d" : "#f5f5f5",
  padding: "10px 16px",
  borderRadius: "16px 16px 16px 4px",
  maxWidth: "80%",
  wordBreak: "break-word",
  "& table": {
    borderCollapse: "collapse",
    width: "100%",
    margin: "8px 0",
    fontSize: "0.85rem",
  },
  "& th, & td": {
    border: `1px solid ${theme.palette.divider}`,
    padding: "6px 10px",
    textAlign: "left",
  },
  "& th": {
    backgroundColor: theme.palette.mode === "dark" ? "#383838" : "#e8e8e8",
    fontWeight: 600,
  },
  "& pre": {
    backgroundColor: theme.palette.mode === "dark" ? "#1e1e1e" : "#e0e0e0",
    padding: "10px",
    borderRadius: "6px",
    overflowX: "auto",
    fontSize: "0.82rem",
    margin: "8px 0",
  },
  "& code": {
    fontFamily: "'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace",
    fontSize: "0.85em",
  },
  "& :not(pre) > code": {
    backgroundColor: theme.palette.mode === "dark" ? "#383838" : "#e0e0e0",
    padding: "2px 5px",
    borderRadius: "4px",
  },
  "& p": { margin: "4px 0" },
  "& ul, & ol": { margin: "4px 0", paddingLeft: "20px" },
  "& h1, & h2, & h3, & h4, & h5, & h6": { margin: "8px 0 4px" },
  "& hr": { border: "none", borderTop: `1px solid ${theme.palette.divider}`, margin: "8px 0" },
  "& a": { color: theme.palette.primary.main },
}));

export default function MessageBubble({ message, onBranch }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (message.answer) {
      navigator.clipboard.writeText(message.answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <Box sx={{ mb: 2 }}>
      {/* Question */}
      {(message.question || (message._files && message._files.length) || message._image) && (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <QuestionBubble>
            {/* Back-compat: older messages stored a single _image dataURL */}
            {message._image && (
              <Box
                component="img"
                src={message._image}
                sx={{ maxWidth: "100%", maxHeight: 200, borderRadius: 1, mb: message.question ? 1 : 0, display: "block" }}
              />
            )}

            {/* Inline thumbnails for attached images */}
            {message._files && message._files.some((f) => f.isImage && f.dataUrl) && (
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, mb: message.question ? 1 : 0 }}>
                {message._files.filter((f) => f.isImage && f.dataUrl).map((f, i) => (
                  <Box
                    key={`img-${f.name}-${i}`}
                    component="img"
                    src={f.dataUrl}
                    alt={f.name}
                    sx={{ maxWidth: 200, maxHeight: 200, borderRadius: 1, display: "block" }}
                  />
                ))}
              </Box>
            )}

            {message.question && (
              <Typography variant="body2">{message.question}</Typography>
            )}

            {/* Chips for non-image attachments */}
            {message._files && message._files.some((f) => !f.isImage) && (
              <Box sx={{ mt: message.question || message._image ? 1 : 0, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                {message._files.filter((f) => !f.isImage).map((f, i) => (
                  <Chip
                    key={`file-${f.name}-${i}`}
                    icon={<AttachFile sx={{ fontSize: 14, color: "rgba(255,255,255,0.85) !important" }} />}
                    label={f.size ? `${f.name} · ${(f.size / 1024).toFixed(1)} KB` : f.name}
                    size="small"
                    sx={{
                      backgroundColor: "rgba(255,255,255,0.18)",
                      color: "#fff",
                      borderRadius: 1,
                      height: 22,
                      "& .MuiChip-label": { fontSize: "0.72rem", px: 0.75 },
                    }}
                  />
                ))}
              </Box>
            )}
          </QuestionBubble>
        </Box>
      )}

      {/* Answer */}
      {message.answer !== null && message.answer !== undefined && (() => {
        // Pull <think> content out of the answer for a separate panel.
        // Live during streaming (openThought), collapsed once closed.
        const { thoughts, answer: answerText, openThought } = splitThinking(message.answer);
        const hasLiveThought = openThought !== null && openThought.trim().length > 0;
        // Final-message path: post_processing_reasoning has already
        // moved <think> blocks into reasoning.steps[*].action="reasoning".
        // Pick those up so we render thoughts even when message.answer
        // no longer carries them.
        const reasoningSteps = (message.reasoning && message.reasoning.steps) || [];
        const thoughtSteps = reasoningSteps.filter((s) =>
          (s.actions || []).some((a) => a.action === "reasoning"));
        const toolSteps = reasoningSteps.filter((s) =>
          (s.actions || []).some((a) => a.action !== "reasoning"));
        const persistedThoughts = thoughtSteps.flatMap((s) =>
          (s.actions || []).filter((a) => a.action === "reasoning").map((a) => a.output));
        // Combine streaming-time thoughts + post-stream persisted ones.
        // De-dupe in case the same content comes through both paths.
        const allThoughts = [...thoughts];
        for (const p of persistedThoughts) {
          if (p && !allThoughts.includes(p)) allThoughts.push(p);
        }
        return (
        <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
          <Box sx={{ maxWidth: "80%" }}>
            <AnswerBubble>
              {/* Plan-and-execute progress — only present when the
                  backend's auto_plan emitted a multi-step plan. Each
                  entry shows a status icon (pending/running/done) and
                  the step name. The synthesis turn is the last entry.
                  Auto-expanded while the run is still in progress
                  (any step !== "done"). */}
              {(() => {
                const planNames = Array.isArray(message.plan) ? message.plan : null;
                if (!planNames || planNames.length === 0) return null;
                const stepStates = Array.isArray(message.step_summaries) ? message.step_summaries : [];
                // Two shapes can arrive here:
                // 1) Live streaming: stepStates already carries
                //    {name, status, summary?} from the SSE events.
                // 2) Persisted final message: the backend stores
                //    [{name, result}] — treat all as "done" since the
                //    run completed by the time the bubble renders.
                const isStreamingShape = stepStates.length > 0 && "status" in stepStates[0];
                let rows;
                if (isStreamingShape) {
                  rows = stepStates;
                } else {
                  rows = [
                    ...planNames.map((name, i) => ({
                      name,
                      status: "done",
                      summary: stepStates[i]?.result || "",
                    })),
                    { name: "Synthesize final answer", status: "done", synthetic: true },
                  ];
                }
                const anyRunning = rows.some((r) => r.status === "running" || r.status === "pending");
                return (
                  <Accordion
                    disableGutters
                    elevation={0}
                    defaultExpanded={anyRunning}
                    sx={{ mb: 1, backgroundColor: "transparent", "&:before": { display: "none" } }}
                  >
                    <AccordionSummary
                      expandIcon={<ExpandMore />}
                      sx={{ minHeight: 28, px: 0, "& .MuiAccordionSummary-content": { my: 0 } }}
                    >
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                        {anyRunning ? <Loop fontSize="small" color="primary" sx={{ animation: "spin 2s linear infinite", "@keyframes spin": { "100%": { transform: "rotate(360deg)" } } }} />
                                    : <CheckCircle fontSize="small" color="success" />}
                        <Typography variant="caption" color="text.secondary">
                          Plan · {rows.filter((r) => r.status === "done").length} / {rows.length} steps
                        </Typography>
                      </Box>
                    </AccordionSummary>
                    <AccordionDetails sx={{ px: 0, pt: 0 }}>
                      <Box component="ol" sx={{ m: 0, pl: 0, listStyle: "none" }}>
                        {rows.map((step, i) => {
                          const icon = step.status === "done"
                            ? <CheckCircle fontSize="inherit" color="success" />
                            : step.status === "running"
                              ? <Loop fontSize="inherit" color="primary" sx={{ animation: "spin 2s linear infinite", "@keyframes spin": { "100%": { transform: "rotate(360deg)" } } }} />
                              : <RadioButtonUnchecked fontSize="inherit" color="action" />;
                          return (
                            <Box
                              key={i}
                              component="li"
                              sx={{
                                display: "flex",
                                alignItems: "flex-start",
                                gap: 1,
                                py: 0.5,
                                fontSize: "0.85rem",
                                opacity: step.status === "pending" ? 0.55 : 1,
                              }}
                            >
                              <Box sx={{ display: "flex", alignItems: "center", pt: "2px", fontSize: "1rem" }}>
                                {icon}
                              </Box>
                              <Box sx={{ flex: 1 }}>
                                <Typography variant="body2" sx={{ fontWeight: step.status === "running" ? 600 : 400 }}>
                                  {step.name}
                                </Typography>
                                {step.summary && (
                                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.25, whiteSpace: "pre-wrap" }}>
                                    {step.summary}
                                  </Typography>
                                )}
                              </Box>
                            </Box>
                          );
                        })}
                      </Box>
                    </AccordionDetails>
                  </Accordion>
                );
              })()}
              {/* Live thinking panel — dim italic, auto-expand while
                  streaming an unterminated <think> block; collapsed
                  after the model closes it. Mirrors `ollama run`. */}
              {(allThoughts.length > 0 || hasLiveThought) && (
                <Accordion
                  disableGutters
                  elevation={0}
                  defaultExpanded={hasLiveThought}
                  sx={{
                    mb: answerText ? 1 : 0,
                    backgroundColor: "transparent",
                    "&:before": { display: "none" },
                  }}
                >
                  <AccordionSummary
                    expandIcon={<ExpandMore />}
                    sx={{ minHeight: 28, px: 0, "& .MuiAccordionSummary-content": { my: 0 } }}
                  >
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <Psychology fontSize="small" color="action" />
                      <Typography variant="caption" color="text.secondary">
                        {hasLiveThought ? "Thinking…" : `${allThoughts.length} thought${allThoughts.length !== 1 ? "s" : ""}`}
                      </Typography>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: 0, pt: 0 }}>
                    <Box
                      sx={{
                        fontStyle: "italic",
                        color: "text.secondary",
                        fontSize: "0.85rem",
                        whiteSpace: "pre-wrap",
                        borderLeft: (theme) => `2px solid ${theme.palette.divider}`,
                        pl: 1.5,
                      }}
                    >
                      {allThoughts.map((t, i) => (
                        <Box key={i} sx={{ mb: i < allThoughts.length - 1 || hasLiveThought ? 1 : 0 }}>{t}</Box>
                      ))}
                      {hasLiveThought && <Box>{openThought}</Box>}
                    </Box>
                  </AccordionDetails>
                </Accordion>
              )}
              <Typography variant="body2" component="div">
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    img: ({ node, ...props }) => (
                      <Box
                        component="img"
                        {...props}
                        sx={{
                          display: "block",
                          maxWidth: "100%",
                          maxHeight: 480,
                          height: "auto",
                          borderRadius: 1,
                          my: 1,
                        }}
                      />
                    ),
                  }}
                >
                  {answerText}
                </ReactMarkdown>
              </Typography>
              {/* Live tool-call panel — populated by SSE
                  `tool_call_started` / `tool_call_completed` events
                  during streaming. Auto-expands so the user can watch
                  the agent work in real-time. Reuses the persisted
                  `Terminal` renderer (same green-on-black look) by
                  mapping each in-flight call into a synthetic
                  reasoning.steps[].actions[] entry; running tools
                  show "…running…" as the output placeholder until
                  the matching completion event lands.

                  Disappears on stream close — the persisted
                  `toolSteps` accordion below takes over. */}
              {Array.isArray(message.live_tool_calls) && message.live_tool_calls.length > 0 && (
                <Accordion
                  disableGutters
                  elevation={0}
                  defaultExpanded
                  sx={{ mt: 1, backgroundColor: "transparent", "&:before": { display: "none" } }}
                >
                  <AccordionSummary expandIcon={<ExpandMore />} sx={{ minHeight: 32, px: 0, "& .MuiAccordionSummary-content": { my: 0 } }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <TerminalOutlined fontSize="small" />
                      <Typography variant="caption" color="text.secondary">
                        {(() => {
                          const total = message.live_tool_calls.length;
                          const running = message.live_tool_calls.filter((c) => c.status === "running").length;
                          if (running > 0) return `Running ${running} of ${total} tool${total !== 1 ? "s" : ""}…`;
                          return `${total} tool call${total !== 1 ? "s" : ""}`;
                        })()}
                      </Typography>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: 0, pt: 0 }}>
                    <Terminal
                      message={{
                        reasoning: {
                          steps: message.live_tool_calls.map((call) => {
                            // `args` arrives JSON-stringified from the
                            // backend (input_preview, capped at 500
                            // chars). Try to parse so Terminal renders
                            // it as a clean object; fall back to the
                            // raw string if it's truncated/invalid.
                            let parsedArgs;
                            try {
                              parsedArgs = call.args ? JSON.parse(call.args) : {};
                            } catch {
                              parsedArgs = { args: call.args };
                            }
                            return {
                              actions: [{
                                action: call.tool,
                                input: parsedArgs,
                                output: call.status === "running"
                                  ? "…running…"
                                  : (call.error || call.output || ""),
                              }],
                            };
                          }),
                        },
                      }}
                    />
                  </AccordionDetails>
                </Accordion>
              )}

              {/* Tool calls — separate accordion from thinking. Reuses
                  the existing terminal renderer with a filtered view of
                  reasoning.steps (action !== "reasoning"). */}
              {toolSteps.length > 0 && (
                <Accordion
                  disableGutters
                  elevation={0}
                  defaultExpanded={false}
                  sx={{ mt: 1, backgroundColor: "transparent", "&:before": { display: "none" } }}
                >
                  <AccordionSummary expandIcon={<ExpandMore />} sx={{ minHeight: 32, px: 0, "& .MuiAccordionSummary-content": { my: 0 } }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <TerminalOutlined fontSize="small" />
                      <Typography variant="caption" color="text.secondary">
                        {toolSteps.length} tool call{toolSteps.length !== 1 ? "s" : ""}
                      </Typography>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: 0, pt: 0 }}>
                    <Terminal message={{ reasoning: { steps: toolSteps } }} />
                  </AccordionDetails>
                </Accordion>
              )}

              {/* Sources — inside the bubble */}
              {message.sources && message.sources.length > 0 && (
                <Accordion
                disableGutters
                elevation={0}
                sx={{ mt: 1, backgroundColor: "transparent", "&:before": { display: "none" } }}
              >
                <AccordionSummary expandIcon={<ExpandMore />} sx={{ minHeight: 32, px: 0, "& .MuiAccordionSummary-content": { my: 0 } }}>
                  <Typography variant="caption" color="text.secondary">
                    {message.sources.length} source{message.sources.length !== 1 ? "s" : ""}
                  </Typography>
                </AccordionSummary>
                <AccordionDetails sx={{ px: 0, pt: 0 }}>
                  {message.sources.map((src, i) => (
                    <Box key={i} sx={{ mb: 1, p: 1, borderRadius: 1, backgroundColor: "action.hover" }}>
                      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
                        <Typography variant="caption" fontWeight="bold">
                          {src.source || `Source ${i + 1}`}
                        </Typography>
                        {src.score !== undefined && (
                          <Chip label={`${(src.score * 100).toFixed(0)}%`} size="small" />
                        )}
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", whiteSpace: "pre-wrap" }}>
                        {typeof src === "string" ? src : (src.text || JSON.stringify(src))}
                      </Typography>
                    </Box>
                  ))}
                </AccordionDetails>
              </Accordion>
              )}
            </AnswerBubble>

            {/* Metadata chips — outside bubble */}
            <Box sx={{ display: "flex", gap: 0.5, mt: 0.5, flexWrap: "wrap", alignItems: "center" }}>
              {message.guard && (
                <Chip icon={<Shield />} label="Guard" size="small" color="warning" variant="outlined" />
              )}
              {message.cached && (
                <Chip icon={<Cached />} label="Cached" size="small" color="info" variant="outlined" />
              )}
              {message.tokens && (message.tokens.input > 0 || message.tokens.output > 0) && (
                <Chip
                  label={`${message.tokens.input + message.tokens.output} tokens`}
                  size="small"
                  variant="outlined"
                />
              )}
              {message.latency_ms > 0 && (
                <Chip
                  icon={<Speed />}
                  label={message.latency_ms > 1000 ? `${(message.latency_ms / 1000).toFixed(1)}s` : `${message.latency_ms}ms`}
                  size="small"
                  variant="outlined"
                />
              )}
              <Tooltip title={copied ? "Copied!" : "Copy answer"}>
                <IconButton size="small" onClick={handleCopy}>
                  <ContentCopy fontSize="small" />
                </IconButton>
              </Tooltip>
              {onBranch && (
                <Tooltip title="Branch conversation from here">
                  <IconButton size="small" onClick={onBranch}>
                    <CallSplit fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          </Box>
        </Box>
        );
      })()}

      {/* Loading state */}
      {message.answer === null && (
        <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
          <AnswerBubble>
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
              Thinking...
            </Typography>
          </AnswerBubble>
        </Box>
      )}
    </Box>
  );
}
