import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  IconButton,
  LinearProgress,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  styled,
} from "@mui/material";
import {
  AutoAwesome,
  CheckCircle,
  Close,
  DeleteSweep,
  Error as ErrorIcon,
  HourglassEmpty,
  PlayArrow,
  Send,
  SmartToy,
  Stop,
  Person,
  Refresh,
} from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import AppCodeEditor from "./AppCodeEditor";

const apiBase = process.env.REACT_APP_RESTAI_API_URL || "";

// --- SSE consumer (same shape as AppDeploy.jsx) ----------------------
//
// Native EventSource doesn't support POST + Authorization header. We use
// fetch + ReadableStream and parse `event:`/`data:` frames by hand.
async function consumeSSE(url, init, signal, onEvent) {
  const res = await fetch(url, { ...init, signal });
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${txt}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let evt = "message";
      let data = null;
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) evt = line.slice(6).trim();
        else if (line.startsWith("data:")) {
          try { data = JSON.parse(line.slice(5).trim()); } catch { /* ignore */ }
        }
      }
      onEvent(evt, data);
    }
  }
}

// --- UI bits ---------------------------------------------------------

const Bubble = styled(Paper)(({ theme, role }) => ({
  padding: theme.spacing(1.5, 2),
  borderRadius: 12,
  maxWidth: "85%",
  alignSelf: role === "user" ? "flex-end" : "flex-start",
  background: role === "user"
    ? theme.palette.primary.main
    : theme.palette.mode === "dark" ? theme.palette.grey[800] : theme.palette.grey[100],
  color: role === "user" ? theme.palette.primary.contrastText : theme.palette.text.primary,
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
}));

// Strip the trailing ```json {...} ``` block from an assistant reply so the
// chat bubble shows only the prose. We keep the structured plan separate.
function stripPlanFence(text) {
  if (!text) return "";
  return text.replace(/```(?:json)?\s*\n?[\s\S]*?\n?```/g, "").trim();
}

// Tests under tests/ are authoritative — fix the app, not the tests. Drop
// any issue attributed to a tests/ path before sending to the LLM.
const dropTestIssues = (issues) =>
  (issues || []).filter((i) => !(i?.path || "").startsWith("tests/"));

// Stable fingerprint of a plan, derived from its summary + every file
// path. Used to remember "this plan was already Approved & Built" across
// dialog close/reopen — see `approvedPlans` in the wizard. Resilient
// to the chat being re-hydrated (message indexes might shift).
function planFingerprint(plan) {
  if (!plan || typeof plan !== "object") return "";
  const phases = Array.isArray(plan.phases) ? plan.phases : [];
  const flatFiles = phases.flatMap((ph) =>
    Array.isArray(ph?.files) ? ph.files.map((f) => f?.path || "") : []
  );
  // Legacy flat-files shape (no phases).
  const legacy = Array.isArray(plan.files)
    ? plan.files.map((f) => f?.path || "")
    : [];
  const paths = [...flatFiles, ...legacy].sort().join("|");
  const summary = (plan.summary || "").trim();
  // djb2 hash — short, no deps, plenty unique for our scale.
  const s = summary + "::" + paths;
  let h = 5381;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h + s.charCodeAt(i)) | 0;
  }
  return `${(h >>> 0).toString(36)}-${paths.length}`;
}

function PlanCard({ plan, overwrite, onOverwriteChange, onApprove, disabled, approved, projectId, token }) {
  const { t } = useTranslation();
  const [showDiff, setShowDiff] = useState(false);
  const [diff, setDiff] = useState(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState(null);
  const [expandedDiffPath, setExpandedDiffPath] = useState(null);

  // Invalidate the cached diff when the plan changes — otherwise
  // re-expanding shows stale content from the previous plan.
  useEffect(() => {
    setDiff(null);
    setDiffError(null);
    setExpandedDiffPath(null);
  }, [plan]);

  const loadDiff = useCallback(async () => {
    if (diff || diffLoading || !projectId) return;
    setDiffLoading(true);
    setDiffError(null);
    try {
      const res = await fetch(`${apiBase}/projects/${projectId}/app/generate/dry-run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Basic " + token,
          "Accept": "application/json",
        },
        body: JSON.stringify({ plan }),
      });
      if (!res.ok) {
        const txt = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}: ${txt}`);
      }
      const body = await res.json();
      setDiff(body);
    } catch (e) {
      setDiffError(e?.message || "diff failed");
    } finally {
      setDiffLoading(false);
    }
  }, [diff, diffLoading, plan, projectId, token]);

  if (!plan) return null;
  const tables = Array.isArray(plan.database) ? plan.database : [];
  const apis = Array.isArray(plan.api) ? plan.api : [];
  const views = Array.isArray(plan.frontend) ? plan.frontend : [];
  // Plan is now phase-shaped. Tolerate the legacy flat-files shape (older
  // chat history) by wrapping it in a single phase for display.
  const phases = Array.isArray(plan.phases) && plan.phases.length > 0
    ? plan.phases
    : (Array.isArray(plan.files)
        ? [{ name: "Build", description: "", files: plan.files }]
        : []);
  const totalFiles = phases.reduce((acc, ph) => acc + (ph.files || []).length, 0);

  return (
    <Paper variant="outlined" sx={{ p: 2, mt: 1, bgcolor: "background.default" }}>
      <Stack spacing={1.5}>
        <Box>
          <Chip label={t("projects.app.gen.planLabel", "Proposed plan")} size="small" color="primary" />
          <Typography variant="body2" sx={{ mt: 1, fontStyle: "italic" }}>
            {plan.summary}
          </Typography>
        </Box>

        {tables.length > 0 && (
          <Box>
            <Typography variant="caption" color="text.secondary">
              {t("projects.app.gen.dbTitle", "Database")}
            </Typography>
            <Table size="small" sx={{ mt: 0.5 }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontSize: 12, py: 0.5 }}>{t("projects.app.gen.colTable", "Table")}</TableCell>
                  <TableCell sx={{ fontSize: 12, py: 0.5 }}>{t("projects.app.gen.colColumns", "Columns")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {tables.map((tbl, i) => (
                  <TableRow key={i}>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: 12, py: 0.5 }}>{tbl.table}</TableCell>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: 11, py: 0.5 }}>
                      {(tbl.columns || []).map((c) => `${c.name} ${c.type || ""}`).join(", ")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}

        {apis.length > 0 && (
          <Box>
            <Typography variant="caption" color="text.secondary">
              {t("projects.app.gen.apiTitle", "JSON API endpoints")}
            </Typography>
            <Table size="small" sx={{ mt: 0.5 }}>
              <TableHead>
                <TableRow>
                  <TableCell sx={{ fontSize: 12, py: 0.5 }}>{t("projects.app.gen.colPath", "Path")}</TableCell>
                  <TableCell sx={{ fontSize: 12, py: 0.5 }}>{t("projects.app.gen.colMethods", "Methods")}</TableCell>
                  <TableCell sx={{ fontSize: 12, py: 0.5 }}>{t("projects.app.gen.colPurpose", "Purpose")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {apis.map((a, i) => (
                  <TableRow key={i}>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: 12, py: 0.5 }}>{a.path}</TableCell>
                    <TableCell sx={{ fontFamily: "monospace", fontSize: 11, py: 0.5 }}>
                      {(a.methods || []).join(" ")}
                    </TableCell>
                    <TableCell sx={{ fontSize: 12, py: 0.5 }}>{a.purpose}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}

        {views.length > 0 && (
          <Box>
            <Typography variant="caption" color="text.secondary">
              {t("projects.app.gen.viewsTitle", "Frontend views")}
            </Typography>
            <Box sx={{ mt: 0.5, display: "flex", gap: 0.5, flexWrap: "wrap" }}>
              {views.map((v, i) => (
                <Tooltip key={i} title={v.purpose || ""}>
                  <Chip size="small" label={v.view} variant="outlined" />
                </Tooltip>
              ))}
            </Box>
          </Box>
        )}

        <Box>
          <Typography variant="caption" color="text.secondary">
            {t("projects.app.gen.phasesTitle", "Build phases ({{phases}} phases · {{files}} files)", {
              phases: phases.length,
              files: totalFiles,
            })}
          </Typography>
          <Box sx={{ mt: 0.5, maxHeight: 240, overflow: "auto", bgcolor: "action.hover", borderRadius: 1, p: 1 }}>
            {phases.map((ph, pi) => (
              <Box key={pi} sx={{ mb: 1 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.25 }}>
                  <Chip
                    label={`${pi + 1}`}
                    size="small"
                    color="primary"
                    sx={{ height: 18, minWidth: 24, fontSize: 11 }}
                  />
                  <Typography component="span" variant="caption" sx={{ fontWeight: 600 }}>
                    {ph.name || `Phase ${pi + 1}`}
                  </Typography>
                  <Typography component="span" variant="caption" color="text.disabled">
                    · {(ph.files || []).length} files
                  </Typography>
                </Box>
                {ph.description && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", pl: 3.5, mb: 0.25 }}>
                    {ph.description}
                  </Typography>
                )}
                <Box sx={{ pl: 3.5 }}>
                  {(ph.files || []).map((f) => (
                    <Box key={f.path} sx={{ display: "flex", gap: 1, fontSize: 12, fontFamily: "monospace" }}>
                      <Typography component="span" sx={{ fontFamily: "monospace", fontSize: 12, color: "text.primary" }}>{f.path}</Typography>
                      <Typography component="span" sx={{ fontSize: 11, color: "text.secondary" }}>— {f.purpose}</Typography>
                    </Box>
                  ))}
                </Box>
              </Box>
            ))}
          </Box>
        </Box>

        {/* Diff preview — collapsible. First expand triggers /dry-run.
            Each file gets a NEW/OVERWRITE chip + a per-file expand
            that shows the current on-disk content in read-only Monaco. */}
        <Divider />
        <Box>
          <Button
            size="small"
            variant="text"
            onClick={() => {
              const opening = !showDiff;
              setShowDiff(opening);
              if (opening) loadDiff();
            }}
          >
            {showDiff
              ? t("projects.app.gen.hideDiff", "▼ Hide changes preview")
              : t("projects.app.gen.showDiff", "▶ Preview changes")}
          </Button>
          {showDiff && (
            <Box sx={{ mt: 1 }}>
              {diffLoading && (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <CircularProgress size={14} />
                  <Typography variant="caption" color="text.secondary">
                    {t("projects.app.gen.diffLoading", "Loading…")}
                  </Typography>
                </Box>
              )}
              {diffError && (
                <Alert severity="error">{diffError}</Alert>
              )}
              {diff && (
                <Box>
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    {t("projects.app.gen.diffSummary", "{{n}} new, {{o}} overwrite", {
                      n: diff.counts?.new || 0,
                      o: diff.counts?.overwrite || 0,
                    })}
                  </Typography>
                  <Box sx={{ maxHeight: 320, overflow: "auto", bgcolor: "action.hover", borderRadius: 1, p: 1 }}>
                    {diff.files.map((f) => {
                      const isOpen = expandedDiffPath === f.path;
                      const isOverwrite = f.change_kind === "overwrite";
                      return (
                        <Box key={f.path} sx={{ mb: 0.5 }}>
                          <Box
                            sx={{ display: "flex", alignItems: "center", gap: 1, cursor: isOverwrite ? "pointer" : "default" }}
                            onClick={() => isOverwrite && setExpandedDiffPath(isOpen ? null : f.path)}
                          >
                            <Chip
                              label={isOverwrite ? "OVERWRITE" : "NEW"}
                              size="small"
                              color={isOverwrite ? "warning" : "success"}
                              sx={{ height: 18, fontSize: 10 }}
                            />
                            <Typography variant="caption" sx={{ fontFamily: "monospace", flexGrow: 1 }}>
                              {f.path}
                            </Typography>
                            {isOverwrite && (
                              <Typography variant="caption" color="text.disabled">
                                {f.size_bytes} b {isOpen ? "▼" : "▶"}
                              </Typography>
                            )}
                          </Box>
                          {isOpen && f.current_content && (
                            <Box sx={{
                              mt: 0.5,
                              ml: 7,
                              height: 200,
                              border: 1,
                              borderColor: "divider",
                              borderRadius: 1,
                              overflow: "hidden",
                              display: "flex",
                              flexDirection: "column",
                            }}>
                              <Typography variant="caption" sx={{ px: 1, py: 0.25, bgcolor: "background.default" }}>
                                {t("projects.app.gen.diffCurrent", "Current on disk (will be replaced):")}
                              </Typography>
                              <AppCodeEditor
                                path={f.path}
                                value={f.current_content}
                                onChange={() => {}}
                                readOnly
                              />
                            </Box>
                          )}
                        </Box>
                      );
                    })}
                  </Box>
                </Box>
              )}
            </Box>
          )}
        </Box>

        <Divider />

        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 1 }}>
          <FormControlLabel
            control={
              <Checkbox
                checked={overwrite}
                onChange={(e) => onOverwriteChange(e.target.checked)}
                size="small"
              />
            }
            label={t("projects.app.gen.overwrite", "Overwrite existing files (your edits will be replaced)")}
          />
          <Button
            variant="contained"
            color="primary"
            startIcon={<PlayArrow />}
            onClick={onApprove}
            disabled={disabled || approved}
          >
            {approved
              ? t("projects.app.gen.approved", "Already built")
              : t("projects.app.gen.approve", "Approve & Build")}
          </Button>
        </Box>
      </Stack>
    </Paper>
  );
}

const FileStatusIcon = ({ status }) => {
  if (status === "done") return <CheckCircle fontSize="small" sx={{ color: "success.main" }} />;
  if (status === "error") return <ErrorIcon fontSize="small" sx={{ color: "error.main" }} />;
  if (status === "in_progress") return <CircularProgress size={14} />;
  return <HourglassEmpty fontSize="small" sx={{ color: "text.disabled" }} />;
};

// --- The wizard ------------------------------------------------------

const INITIAL_GREETING = (t) => ({
  role: "assistant",
  content: t(
    "projects.app.gen.greeting",
    "Hi! Tell me what app you want to build — for example: \"online flower shop with products, cart, and checkout\". I'll propose a plan; you can refine it as much as you like before I write any code."
  ),
  plan: null,
});

export default function AppGenerateWizard({ open, onClose, projectId, project, token, onAfterBuild }) {
  const { t } = useTranslation();
  const [step, setStep] = useState("chat"); // chat | executing | done
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streamingReply, setStreamingReply] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [overwrite, setOverwrite] = useState(true);
  // Track which plan messages have already been Approved & Built so the
  // button stays disabled when the user revisits the wizard with an old
  // plan card visible. We key by a stable content fingerprint, not by
  // message index, because chat hydrates from the server and indexes
  // could shift if anything ever inserts a message. Persisted to
  // localStorage per project so close+reopen of the dialog keeps the
  // disabled state.
  const approvedStorageKey = `restai.app.${projectId}.approvedPlans`;
  const [approvedPlans, setApprovedPlans] = useState(() => {
    try {
      const raw = window.localStorage.getItem(approvedStorageKey);
      return new Set(raw ? JSON.parse(raw) : []);
    } catch {
      return new Set();
    }
  });
  const persistApprovedPlans = useCallback((next) => {
    try {
      window.localStorage.setItem(approvedStorageKey, JSON.stringify([...next]));
    } catch {
      /* quota / disabled storage — degrade silently, in-memory still works */
    }
  }, [approvedStorageKey]);
  const abortRef = useRef(null);
  const scrollRef = useRef(null);

  const [progress, setProgress] = useState({ files: [], current: null });
  const [currentText, setCurrentText] = useState("");
  const [summary, setSummary] = useState(null);
  // Post-build validation: { running: bool, result: {ok, summary, issues}|null }
  const [validation, setValidation] = useState({ running: false, result: null });
  // Auto-fix loop state. `attempts` is per-build (resets on every fresh
  // Approve & Build); `running` flips while a fix iteration is in flight;
  // `halted` set by the Stop button so the recursion bails between turns.
  const AUTOFIX_MAX = 2;
  const [autoFix, setAutoFix] = useState({ attempts: 0, running: false, halted: false, status: "" });
  const autoFixHaltedRef = useRef(false);
  // Re-entry guard. Set true on entry, cleared on exit. Prevents two
  // parallel runAutoFix calls if multiple call sites fire in the same
  // tick (or an old call fires alongside a new one after a state change).
  const autoFixActiveRef = useRef(false);
  // Forward ref so startExecute (declared above runAutoFix in this file)
  // can fire auto-fix immediately after validation returns, instead of
  // depending on the useEffect to pick up the validation state change
  // — which has proven flaky on some render-timing paths.
  const runAutoFixRef = useRef(null);
  // Forward ref so the no-JSON auto-retry block at the END of sendMessage
  // can call sendMessage again without TDZ headaches.
  const sendMessageRef = useRef(null);

  // Hydrate the chat from the server's persisted thread (agent2.memory,
  // Redis-backed) every time the dialog opens. This means a user who
  // closes the wizard, reloads, comes back next week, on a different
  // browser, etc. lands back in the same conversation. If the thread is
  // empty, seed with the initial greeting (NOT persisted — it's just a UI
  // prompt, the server thread starts on the first user message).
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetch(`${apiBase}/projects/${projectId}/app/chat`, {
      headers: { "Authorization": "Basic " + token, "Accept": "application/json" },
    })
      .then((res) => res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`)))
      .then((body) => {
        if (cancelled) return;
        const persisted = (body.messages || []).map((m) => ({
          role: m.role,
          content: m.content || "",
          plan: m.plan || null,
        }));
        if (persisted.length === 0) {
          setMessages([INITIAL_GREETING(t)]);
        } else {
          setMessages(persisted);
        }
      })
      .catch(() => {
        if (cancelled) return;
        // Fall back to the local greeting if the API failed; the next
        // send will surface a real error if /plan is also broken.
        setMessages((prev) => prev.length > 0 ? prev : [INITIAL_GREETING(t)]);
      });
    return () => { cancelled = true; };
  }, [open, projectId, token, t]);

  // Auto-scroll the chat to bottom on new messages / streaming text.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingReply, streaming]);

  // Latest plan is the last assistant message that has one.
  const latestPlan = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i--) {
      const m = messages[i];
      if (m.role === "assistant" && m.plan) return { plan: m.plan, index: i };
    }
    return null;
  }, [messages]);

  // ---- Send chat message ----
  // Optionally accepts an explicit message text + opts so internal
  // call sites (the no-JSON auto-retry, future programmatic flows) can
  // bypass the input field. opts.isAutoRetry suppresses the auto-retry
  // block at the bottom so a retry that ALSO returns no JSON doesn't
  // loop forever.
  const sendMessage = useCallback(async (overrideText, opts = {}) => {
    const text = (typeof overrideText === "string" ? overrideText : input).trim();
    if (!text || streaming) return;
    const isAutoRetry = !!opts.isAutoRetry;

    // Server is the source of truth for chat history (agent2.memory). We
    // only POST the new user message; the server pulls the persisted
    // thread, appends, runs the LLM, and saves the assistant reply.
    const userMsg = { role: "user", content: text };

    setMessages((prev) => [...prev, userMsg]);
    if (typeof overrideText !== "string") setInput("");
    setStreamingReply("");
    setStreaming(true);
    abortRef.current = new AbortController();

    let acc = "";
    let finalPlan = null;
    let finalReply = "";
    try {
      await consumeSSE(
        `${apiBase}/projects/${projectId}/app/generate/plan`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Basic " + token,
            "Accept": "text/event-stream",
          },
          body: JSON.stringify({ message: text }),
        },
        abortRef.current.signal,
        (evt, data) => {
          if (evt === "plan_chunk" && data?.text) {
            acc += data.text;
            setStreamingReply(acc);
          } else if (evt === "plan_complete") {
            finalPlan = data?.plan ?? null;
            finalReply = data?.reply ?? acc;
          } else if (evt === "error") {
            throw new Error(data?.message || "plan stream error");
          }
        },
      );
    } catch (e) {
      if (e?.name !== "AbortError") {
        toast.error(e?.message || "plan failed");
      }
      setStreaming(false);
      setStreamingReply("");
      return;
    }

    setMessages((prev) => [
      ...prev,
      { role: "assistant", content: stripPlanFence(finalReply) || finalReply, plan: finalPlan },
    ]);
    setStreamingReply("");
    setStreaming(false);
    abortRef.current = null;

    // Auto-retry: if the LLM described what it would build but forgot
    // the required JSON plan block, immediately re-prompt for the JSON.
    // Skip if the reply looks like a clarifying question (ends with '?'
    // or has explicit asking markers). Capped at one retry per turn —
    // isAutoRetry from opts ensures a retry that ALSO returns no JSON
    // doesn't loop forever.
    if (!isAutoRetry && !finalPlan && finalReply) {
      const trimmed = finalReply.trim();
      const looksLikeQuestion =
        trimmed.endsWith("?") ||
        /\b(should|would|could|do you want|which|how)\b.*\?/i.test(trimmed) ||
        /\bclarif\w*/i.test(trimmed);
      if (!looksLikeQuestion) {
        setTimeout(() => {
          if (sendMessageRef.current) {
            sendMessageRef.current(
              "You described the plan but didn't include the required ```json``` plan block. Please now emit the structured JSON plan as specified in the system prompt — same description, just add the JSON block at the end of your reply.",
              { isAutoRetry: true }
            );
          }
        }, 50);
      }
    }
  }, [input, streaming, projectId, token]);

  // Wire the ref so the auto-retry inside sendMessage can call sendMessage
  // again without TDZ issues.
  sendMessageRef.current = sendMessage;

  const cancelStream = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    setStreaming(false);
    setStreamingReply("");
  }, []);

  // ---- Validation (used by both Approve & Build's post-step and the
  // auto-fix loop). Defined before startExecute so React deps don't
  // hit a temporal dead zone at render time. ----
  const runValidate = useCallback(async () => {
    setValidation({ running: true, result: null });
    try {
      const res = await fetch(`${apiBase}/projects/${projectId}/app/validate`, {
        method: "POST",
        headers: { "Authorization": "Basic " + token, "Accept": "application/json" },
      });
      if (!res.ok) {
        // Try to surface the FastAPI `detail` field — much friendlier than
        // "HTTP 502" when the LLM provider hiccups or the proxy times out.
        let detail = "";
        try {
          const body = await res.json();
          detail = body?.detail || "";
        } catch {
          /* body wasn't JSON — fall through to status code */
        }
        const reason = res.status === 502 ? "AI reviewer unreachable"
          : res.status === 504 ? "AI reviewer timed out"
          : res.status === 429 ? "AI reviewer rate-limited"
          : `HTTP ${res.status}`;
        throw new Error(detail ? `${reason}: ${detail}` : reason);
      }
      const body = await res.json();
      setValidation({ running: false, result: body });
      return body;
    } catch (e) {
      const fail = { ok: false, summary: e?.message || "validation failed", issues: [] };
      setValidation({ running: false, result: fail });
      return fail;
    }
  }, [projectId, token]);

  // ---- Approve & Build ----
  const startExecute = useCallback(async () => {
    if (!latestPlan) return;
    // Mark this plan as consumed so re-opening the wizard with the
    // already-built plan card visible doesn't let the user accidentally
    // re-trigger the build. Fingerprinted by content (not message
    // index) so it survives chat re-hydration; persisted to localStorage
    // so it survives dialog close/reopen.
    const fp = planFingerprint(latestPlan.plan);
    if (fp) {
      setApprovedPlans((prev) => {
        const next = new Set(prev);
        next.add(fp);
        persistApprovedPlans(next);
        return next;
      });
    }
    setStep("executing");
    // Flatten phases into a single file list for the progress sidebar.
    // Each entry carries phase metadata so the UI can group/highlight.
    const planObj = latestPlan.plan;
    const phasesArr = Array.isArray(planObj.phases) && planObj.phases.length > 0
      ? planObj.phases
      : (Array.isArray(planObj.files)
          ? [{ name: "Build", description: "", files: planObj.files }]
          : []);
    const flatFiles = [];
    phasesArr.forEach((ph, pi) => {
      (ph.files || []).forEach((f) => {
        flatFiles.push({
          ...f,
          status: "pending",
          phase: ph.name || `Phase ${pi + 1}`,
          phaseIndex: pi + 1,
        });
      });
    });
    setProgress({ files: flatFiles, current: null, currentPhase: null, phaseIssues: [] });
    setCurrentText("");
    setSummary(null);
    // Fresh build → fresh auto-fix budget. Halted flag resets too so the
    // user can retry cleanly after a previous Stop.
    setAutoFix({ attempts: 0, running: false, halted: false, status: "" });
    autoFixHaltedRef.current = false;
    abortRef.current = new AbortController();

    let acc = "";
    try {
      await consumeSSE(
        `${apiBase}/projects/${projectId}/app/generate/execute`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Basic " + token,
            "Accept": "text/event-stream",
          },
          body: JSON.stringify({ plan: latestPlan.plan, overwrite }),
        },
        abortRef.current.signal,
        (evt, data) => {
          if (evt === "contracts_start") {
            // Sketch-then-fill is generating shared contracts before any
            // code. Show as the current "phase" so the user sees activity
            // even though this isn't part of the plan's phases array.
            setProgress((p) => ({ ...p, currentPhase: "Sketching contracts" }));
            setCurrentText("");
          } else if (evt === "contracts_done") {
            setProgress((p) => ({ ...p, currentPhase: null }));
            // The contracts text isn't shown in the editor — it's
            // injected into every per-file LLM prompt server-side.
          } else if (evt === "phase_start" && data?.name) {
            // Highlight the current phase header in the sidebar.
            setProgress((p) => ({ ...p, currentPhase: data.name }));
          } else if (evt === "phase_done") {
            // Phase completed; clear the highlight (next phase_start will set again).
            setProgress((p) => ({ ...p, currentPhase: null }));
          } else if (evt === "phase_check") {
            // Per-phase runtime probes — accumulate issues so the user
            // can see what broke at each stage.
            const issues = (data && data.issues) || [];
            if (issues.length > 0) {
              setProgress((p) => ({
                ...p,
                phaseIssues: [
                  ...(p.phaseIssues || []),
                  { phase: data.name, index: data.index, issues },
                ],
              }));
            }
          } else if (evt === "phase_fix_start" && data?.targets) {
            // Inline auto-fix kicked in mid-build. Highlight the
            // current phase header to indicate a repair is in flight.
            setProgress((p) => ({
              ...p,
              currentPhase: `${data.phase} (fixing ${data.targets.length} file${data.targets.length === 1 ? "" : "s"}…)`,
            }));
          } else if (evt === "phase_fix_done") {
            // Repair landed. Mark the fixed files as in_progress→done
            // briefly so the file list reflects the rewrite.
            const fixed = (data && data.fixed) || [];
            setProgress((p) => ({
              ...p,
              currentPhase: null,
              files: p.files.map((f) =>
                fixed.includes(f.path) ? { ...f, status: "done", fixed: true } : f
              ),
            }));
          } else if (evt === "file_start" && data?.path) {
            acc = "";
            setCurrentText("");
            setProgress((p) => ({
              ...p,
              files: p.files.map((f) => f.path === data.path ? { ...f, status: "in_progress" } : f),
              current: data.path,
            }));
          } else if (evt === "file_delta" && data?.text) {
            acc += data.text;
            setCurrentText(acc);
          } else if (evt === "file_done" && data?.path) {
            setProgress((p) => ({
              ...p,
              files: p.files.map((f) => f.path === data.path ? { ...f, status: "done", etag: data.etag } : f),
              current: null,
            }));
          } else if (evt === "file_error" && data?.path) {
            setProgress((p) => ({
              ...p,
              files: p.files.map((f) => f.path === data.path ? { ...f, status: "error", error: data.error } : f),
              current: null,
            }));
          } else if (evt === "complete") {
            setSummary(data);
          } else if (evt === "error") {
            throw new Error(data?.message || "execute stream error");
          }
        },
      );
      setStep("done");
      if (onAfterBuild) onAfterBuild();
      // Run validation, then immediately kick off the auto-fix loop if
      // the reviewer flagged issues. Done synchronously here (instead of
      // via the useEffect) so the chain is deterministic and doesn't
      // depend on React effect-scheduling timing.
      const v = await runValidate();
      if (
        v && !v.ok
        && Array.isArray(v.issues) && v.issues.length > 0
        && runAutoFixRef.current
        && !autoFixHaltedRef.current
      ) {
        runAutoFixRef.current(v.issues);
      }
    } catch (e) {
      if (e?.name !== "AbortError") {
        toast.error(e?.message || "execute failed");
      }
      // Even if cancelled, keep showing what was written so far.
      setStep("done");
      if (onAfterBuild) onAfterBuild();
    } finally {
      abortRef.current = null;
    }
  }, [latestPlan, projectId, token, overwrite, onAfterBuild, runValidate]);

  const cancelExecute = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
  }, []);

  // ---- Auto-fix loop ----
  //
  // When validation finds issues, automatically run a fix iteration:
  //   1. Push a synthetic "fix these issues" chat message (visible to the
  //      user — the conversation captures what the agent did).
  //   2. Stream the LLM's plan via the same /generate/plan endpoint.
  //   3. Auto-execute the plan via /generate/execute.
  //   4. Re-run /validate.
  //   5. If issues remain AND attempts < AUTOFIX_MAX, recurse.
  //
  // Cap at AUTOFIX_MAX iterations per build cycle so a stubborn LLM can't
  // burn unlimited tokens. The Stop Auto-fix button flips
  // `autoFixHaltedRef.current` between iterations.
  const runAutoFix = useCallback(async (issues) => {
    if (autoFixHaltedRef.current) return;
    if (autoFixActiveRef.current) return;  // re-entry guard
    autoFixActiveRef.current = true;
    try {
    setAutoFix((p) => ({ ...p, attempts: p.attempts + 1, running: true, status: "asking" }));

    const fixableIssues = dropTestIssues(issues);
    if (fixableIssues.length === 0) {
      // Nothing for the LLM to act on without modifying tests. Bail.
      setAutoFix((p) => ({ ...p, running: false, status: "" }));
      autoFixActiveRef.current = false;
      return;
    }

    // Compose the fix prompt (visible in chat thread). We instruct the
    // LLM to emit an INCREMENTAL plan — only the files that need changes
    // — matching the system prompt's Mode B contract. Critically we tell
    // it that "missing file" issues MUST be resolved by CREATING the
    // file, not by removing the importer (the most common LLM mistake).
    const fixMsg =
      "The AI code reviewer flagged these issues with the latest build. " +
      "Please fix them and emit an incremental plan that only includes the " +
      "files that need to change OR new files that need to be created.\n\n" +
      "RULES:\n" +
      "- If an issue says a file is referenced but missing (e.g. \"Could not " +
      "resolve '../api'\" or \"file does not exist but is imported by …\"), " +
      "CREATE the missing file. Do NOT remove the import. The importer is " +
      "almost always correct; the missing dependency is what needs adding.\n" +
      "- If a PHP endpoint returns HTTP 500 / parse error, fix the SYNTAX " +
      "in that PHP file. Don't delete the file or change its callers.\n" +
      "- If the SPA shell is missing the mount point or script tag, fix " +
      "public/index.html so the TypeScript bundle can mount.\n" +
      "- Tests under tests/ are AUTHORITATIVE. If a test failure surfaces, " +
      "fix the application code the test exercises, NEVER the test file " +
      "itself. Test files must not appear in your plan.files.\n" +
      "- Your plan.files array MUST list every file you intend to write or " +
      "create. Only the files you list will be touched.\n\n" +
      "Issues to fix:\n" +
      fixableIssues.map((i) => `- [${i.severity || "?"}] ${i.path}: ${i.message}`).join("\n");

    setMessages((prev) => [...prev, { role: "user", content: fixMsg }]);
    setStreamingReply("");

    // 1) Plan — stream and capture the resulting plan dict.
    let planAcc = "";
    let fixPlan = null;
    let fixReply = "";
    try {
      await consumeSSE(
        `${apiBase}/projects/${projectId}/app/generate/plan`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Basic " + token,
            "Accept": "text/event-stream",
          },
          body: JSON.stringify({ message: fixMsg }),
        },
        // Auto-fix is interruptible by the user's Stop button; piggyback
        // on the existing abortRef so a single Stop kills both phases.
        (abortRef.current = new AbortController()).signal,
        (evt, data) => {
          if (evt === "plan_chunk" && data?.text) {
            planAcc += data.text;
            setStreamingReply(planAcc);
          } else if (evt === "plan_complete") {
            fixPlan = data?.plan ?? null;
            fixReply = data?.reply ?? planAcc;
          } else if (evt === "error") {
            throw new Error(data?.message || "plan stream error");
          }
        },
      );
    } catch (e) {
      setStreamingReply("");
      setMessages((prev) => [...prev, { role: "assistant", content: `(auto-fix plan failed: ${e?.message || e})`, plan: null }]);
      setAutoFix((p) => ({ ...p, running: false, status: "" }));
      return;
    }
    setStreamingReply("");
    setMessages((prev) => [...prev, { role: "assistant", content: stripPlanFence(fixReply) || fixReply, plan: fixPlan }]);

    if (autoFixHaltedRef.current) {
      setAutoFix((p) => ({ ...p, running: false, status: "" }));
      return;
    }
    if (!fixPlan || !Array.isArray(fixPlan.files) || fixPlan.files.length === 0) {
      // LLM asked a clarifying question instead of producing a plan.
      // Stop the loop — user must take over.
      setAutoFix((p) => ({ ...p, running: false, status: "" }));
      return;
    }

    // 2) Execute the fix plan. Per-file status updates so the user sees
    // actual progress — file_start fires per file, file_delta fires as the
    // LLM streams content, file_done fires after the file lands on disk.
    // Without this the status was stuck on plain "writing files…" for the
    // entire run because we only updated on file_done.
    const totalFiles = (fixPlan.files || []).length;
    let writtenCount = 0;
    let errorCount = 0;
    setAutoFix((p) => ({ ...p, status: `writing 0/${totalFiles}` }));
    try {
      await consumeSSE(
        `${apiBase}/projects/${projectId}/app/generate/execute`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": "Basic " + token,
            "Accept": "text/event-stream",
          },
          body: JSON.stringify({ plan: fixPlan, overwrite: true }),
        },
        (abortRef.current = new AbortController()).signal,
        (evt, data) => {
          if (evt === "file_start" && data?.path) {
            setAutoFix((p) => ({
              ...p,
              status: `${data.index || writtenCount + 1}/${data.total || totalFiles} ${data.path}`,
            }));
          } else if (evt === "file_done" && data?.path) {
            writtenCount += 1;
            setAutoFix((p) => ({ ...p, status: `wrote ${writtenCount}/${totalFiles}` }));
          } else if (evt === "file_error" && data?.path) {
            errorCount += 1;
            setAutoFix((p) => ({
              ...p,
              status: `${writtenCount} ok, ${errorCount} failed`,
            }));
          } else if (evt === "complete") {
            setAutoFix((p) => ({
              ...p,
              status: `wrote ${writtenCount}/${totalFiles}, re-checking…`,
            }));
          } else if (evt === "error") {
            throw new Error(data?.message || "execute stream error");
          }
        },
      );
    } catch (e) {
      setAutoFix((p) => ({ ...p, running: false, status: "" }));
      toast.error(`Auto-fix execute failed: ${e?.message || e}`);
      autoFixActiveRef.current = false;
      return;
    }

    if (onAfterBuild) onAfterBuild();
    if (autoFixHaltedRef.current) {
      setAutoFix((p) => ({ ...p, running: false, status: "" }));
      return;
    }

    // 3) Re-validate.
    setAutoFix((p) => ({ ...p, status: "rechecking" }));
    const v = await runValidate();

    // 4) Recurse if still broken AND we have iterations left AND not halted.
    if (
      !autoFixHaltedRef.current
      && v && !v.ok && Array.isArray(v.issues) && v.issues.length > 0
    ) {
      // Read the latest attempts via setter callback to avoid stale closure.
      let shouldRecurse = false;
      setAutoFix((p) => {
        shouldRecurse = p.attempts < AUTOFIX_MAX;
        return p;
      });
      if (shouldRecurse) {
        setAutoFix((p) => ({ ...p, running: false, status: "" }));
        // Defer to next tick so React commits before the next iteration
        // mutates state again.
        setTimeout(() => runAutoFix(v.issues), 0);
        return;
      }
    }
    setAutoFix((p) => ({ ...p, running: false, status: "" }));
    } finally {
      autoFixActiveRef.current = false;
    }
  }, [projectId, token, runValidate, onAfterBuild]);

  // Bridge ref so callers declared earlier in the file (startExecute) can
  // invoke runAutoFix without TDZ headaches. Updated on every render so
  // the latest closure is always the one that fires.
  runAutoFixRef.current = runAutoFix;

  const stopAutoFix = useCallback(() => {
    autoFixHaltedRef.current = true;
    if (abortRef.current) abortRef.current.abort();
    setAutoFix((p) => ({ ...p, running: false, halted: true, status: "" }));
  }, []);

  // (Auto-fix now triggered explicitly by startExecute after runValidate
  // returns — no useEffect needed. The earlier effect-based trigger had
  // race conditions with React's render scheduling that made it miss
  // events on some paths.)

  // ---- Reset chat (DELETE the persisted thread) ----
  const resetChat = useCallback(async () => {
    if (streaming) return;
    if (!window.confirm(t("projects.app.gen.resetConfirm", "Clear the planning chat for this project? Files on disk are not touched."))) {
      return;
    }
    try {
      const res = await fetch(`${apiBase}/projects/${projectId}/app/chat`, {
        method: "DELETE",
        headers: { "Authorization": "Basic " + token },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setMessages([INITIAL_GREETING(t)]);
      setInput("");
      setStreamingReply("");
      // Wipe the approved-plans memory too — the plans those fingerprints
      // referred to are gone now, and a future identical-shaped plan
      // shouldn't inherit the disabled state from a deleted ancestor.
      setApprovedPlans(new Set());
      try { window.localStorage.removeItem(approvedStorageKey); } catch {}
      toast.success(t("projects.app.gen.resetDone", "Chat cleared"));
    } catch (e) {
      toast.error(e?.message || "reset failed");
    }
  }, [projectId, token, streaming, t]);

  // ---- Done handlers ----
  const continueChat = useCallback(() => {
    // If validation left unresolved issues (auto-fix gave up, or the
    // user hit Stop, or 2 iterations weren't enough), pre-fill the chat
    // input with a formatted "fix these" message — the user just clicks
    // Send instead of copy-pasting from the AI review panel.
    const issues = (validation.result && !validation.result.ok)
      ? dropTestIssues(validation.result.issues)
      : [];
    if (issues.length > 0) {
      const formatted =
        "These issues are still failing on the latest build — please fix them. " +
        "If a file is referenced but missing, CREATE it (don't just remove the import). " +
        "Tests under tests/ are authoritative — fix the app, not the tests. " +
        "Emit an incremental plan with only the files that need to change or be added:\n\n" +
        issues.map((i) => `- [${i.severity || "?"}] ${i.path}: ${i.message}`).join("\n");
      setInput(formatted);
    }
    // Reset auto-fix budget so the next manually-triggered fix gets full
    // retry budget (in case the user wants the loop to take another crack
    // after their refinement).
    setAutoFix({ attempts: 0, running: false, halted: false, status: "" });
    autoFixHaltedRef.current = false;

    setStep("chat");
    setSummary(null);
    setProgress({ files: [], current: null });
    setCurrentText("");
  }, [validation]);

  const closeAndReset = useCallback(() => {
    onClose();
    // Reset on next open
    setTimeout(() => {
      setStep("chat");
      setMessages([]);
      setInput("");
      setStreamingReply("");
      setStreaming(false);
      setProgress({ files: [], current: null });
      setCurrentText("");
      setSummary(null);
      setOverwrite(true);
    }, 250);
  }, [onClose]);

  return (
    <Dialog
      open={open}
      onClose={() => !streaming && step !== "executing" && onClose()}
      fullWidth
      maxWidth="md"
      PaperProps={{ sx: { height: "85vh" } }}
    >
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, pr: 1 }}>
        <AutoAwesome fontSize="small" />
        <span>{t("projects.app.gen.title", "Build app with AI")}</span>
        {project?.llm && (
          <Chip
            label={project.llm}
            size="small"
            variant="outlined"
            sx={{ ml: "auto", mr: 1 }}
          />
        )}
        {step === "chat" && (
          <Tooltip title={t("projects.app.gen.resetChat", "Clear chat history")}>
            <span>
              <IconButton
                size="small"
                onClick={resetChat}
                disabled={streaming || messages.length <= 1}
              >
                <DeleteSweep fontSize="small" />
              </IconButton>
            </span>
          </Tooltip>
        )}
        <IconButton size="small" onClick={onClose} disabled={step === "executing"}>
          <Close fontSize="small" />
        </IconButton>
      </DialogTitle>

      <DialogContent dividers sx={{ display: "flex", flexDirection: "column", p: 0 }}>
        {step === "chat" && (
          <Box sx={{ display: "flex", flexDirection: "column", flexGrow: 1, minHeight: 0 }}>
            <Box ref={scrollRef} sx={{ flexGrow: 1, overflow: "auto", p: 2 }}>
              <Stack spacing={1.5}>
                {messages.map((m, i) => (
                  <Box key={i} sx={{ display: "flex", gap: 1, alignItems: "flex-start", flexDirection: m.role === "user" ? "row-reverse" : "row" }}>
                    {m.role === "assistant" ? <SmartToy fontSize="small" sx={{ mt: 0.5, color: "text.secondary" }} /> : <Person fontSize="small" sx={{ mt: 0.5, color: "primary.main" }} />}
                    <Box sx={{ display: "flex", flexDirection: "column", alignItems: m.role === "user" ? "flex-end" : "flex-start", flexGrow: 1 }}>
                      <Bubble role={m.role} variant="outlined">
                        <Typography variant="body2" component="div">
                          {m.content || (m.plan ? "(see plan below)" : "")}
                        </Typography>
                      </Bubble>
                      {m.role === "assistant" && m.plan && (
                        <Box sx={{ alignSelf: "stretch", maxWidth: "85%" }}>
                          <PlanCard
                            plan={m.plan}
                            overwrite={overwrite}
                            onOverwriteChange={setOverwrite}
                            onApprove={startExecute}
                            disabled={streaming || (latestPlan && latestPlan.index !== i)}
                            approved={approvedPlans.has(planFingerprint(m.plan))}
                            projectId={projectId}
                            token={token}
                          />
                        </Box>
                      )}
                    </Box>
                  </Box>
                ))}

                {streaming && (
                  <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                    <SmartToy fontSize="small" sx={{ mt: 0.5, color: "text.secondary" }} />
                    <Bubble role="assistant" variant="outlined" sx={{ width: "85%" }}>
                      <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", opacity: 0.85 }}>
                        {streamingReply || t("projects.app.gen.thinking", "Thinking…")}
                      </Typography>
                    </Bubble>
                  </Box>
                )}
              </Stack>
            </Box>

            <Divider />

            <Box sx={{ p: 2 }}>
              <Box sx={{ display: "flex", gap: 1, alignItems: "flex-end" }}>
                <TextField
                  fullWidth
                  multiline
                  minRows={1}
                  maxRows={6}
                  placeholder={t("projects.app.gen.placeholder", "Describe your app, or refine the proposed plan…")}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  disabled={streaming}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                />
                {streaming ? (
                  <Button variant="outlined" color="warning" startIcon={<Stop />} onClick={cancelStream}>
                    {t("projects.app.gen.cancel", "Cancel")}
                  </Button>
                ) : (
                  <Button variant="contained" startIcon={<Send />} onClick={sendMessage} disabled={!input.trim()}>
                    {t("projects.app.gen.send", "Send")}
                  </Button>
                )}
              </Box>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                {t("projects.app.gen.kbdHint", "Cmd/Ctrl+Enter to send")}
              </Typography>
            </Box>
          </Box>
        )}

        {step === "executing" && (
          <Box sx={{ display: "flex", flexDirection: { xs: "column", md: "row" }, flexGrow: 1, minHeight: 0 }}>
            <Box sx={{ width: { xs: "100%", md: 280 }, p: 2, borderRight: { md: 1 }, borderColor: { md: "divider" }, overflow: "auto" }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t("projects.app.gen.execTitle", "Building {{n}} files", { n: progress.files.length })}
              </Typography>
              <LinearProgress
                variant="determinate"
                value={progress.files.length === 0 ? 0 : (progress.files.filter((f) => f.status === "done" || f.status === "error").length * 100) / progress.files.length}
                sx={{ mb: 2 }}
              />
              <Stack spacing={0.5}>
                {/* Group flat file list by phase. Highlight the current
                    phase header and dim the others. */}
                {(() => {
                  const groups = [];
                  let lastPhase = null;
                  let groupIdx = -1;
                  for (const f of progress.files) {
                    const ph = f.phase || "Build";
                    if (ph !== lastPhase) {
                      lastPhase = ph;
                      groupIdx += 1;
                      groups.push({ phase: ph, phaseIndex: f.phaseIndex || groupIdx + 1, files: [] });
                    }
                    groups[groupIdx].files.push(f);
                  }
                  return groups.map((g, gi) => {
                    const isCurrent = progress.currentPhase === g.phase;
                    const allDone = g.files.every((f) => f.status === "done" || f.status === "error");
                    return (
                      <Box key={gi} sx={{ mb: 0.5 }}>
                        <Box sx={{
                          display: "flex",
                          alignItems: "center",
                          gap: 0.5,
                          mb: 0.25,
                          px: 0.5,
                          py: 0.25,
                          borderRadius: 0.5,
                          bgcolor: isCurrent ? "primary.main" : (allDone ? "action.hover" : "transparent"),
                          color: isCurrent ? "primary.contrastText" : "text.secondary",
                          opacity: !isCurrent && allDone ? 0.7 : 1,
                        }}>
                          <Typography variant="caption" sx={{ fontWeight: 700 }}>
                            {g.phaseIndex}. {g.phase}
                          </Typography>
                        </Box>
                        {g.files.map((f) => (
                          <Box key={f.path} sx={{ display: "flex", alignItems: "center", gap: 1, pl: 1 }}>
                            <FileStatusIcon status={f.status} />
                            <Typography variant="caption" sx={{ fontFamily: "monospace", flexGrow: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {f.path}
                            </Typography>
                          </Box>
                        ))}
                      </Box>
                    );
                  });
                })()}
              </Stack>
            </Box>
            <Box sx={{ flexGrow: 1, p: 2, display: "flex", flexDirection: "column", minHeight: 0 }}>
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace", mb: 0.5 }}>
                {progress.current || t("projects.app.gen.execIdle", "Waiting for next file…")}
              </Typography>
              <Box
                sx={{
                  // display:flex makes the AppCodeEditor's flexGrow:1 work;
                  // explicit height ensures Monaco's height:100% propagates.
                  display: "flex",
                  flexDirection: "column",
                  flexGrow: 1,
                  minHeight: 360,
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 1,
                  overflow: "hidden",
                }}
              >
                {progress.current ? (
                  <AppCodeEditor path={progress.current} value={currentText} onChange={() => {}} readOnly />
                ) : (
                  <Box sx={{ p: 2 }}>
                    <Typography variant="caption" color="text.disabled">
                      {t("projects.app.gen.execHint", "Each file streams here as the LLM writes it.")}
                    </Typography>
                  </Box>
                )}
              </Box>
            </Box>
          </Box>
        )}

        {step === "done" && summary && (
          <Box sx={{ p: 3 }}>
            <Stack spacing={2}>
              <Alert severity={summary.failed?.length ? "warning" : "success"}>
                {t("projects.app.gen.doneSummary", "Wrote {{w}} file(s), {{f}} failed", {
                  w: summary.written?.length || 0,
                  f: summary.failed?.length || 0,
                })}
              </Alert>
              {summary.written?.length > 0 && (
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t("projects.app.gen.writtenLabel", "Written:")}
                  </Typography>
                  <Box sx={{ mt: 0.5, p: 1, bgcolor: "action.hover", borderRadius: 1, maxHeight: 180, overflow: "auto" }}>
                    {summary.written.map((p) => (
                      <Typography key={p} variant="caption" sx={{ fontFamily: "monospace", display: "block" }}>
                        ✓ {p}
                      </Typography>
                    ))}
                  </Box>
                </Box>
              )}
              {summary.failed?.length > 0 && (
                <Box>
                  <Typography variant="caption" color="error">
                    {t("projects.app.gen.failedLabel", "Failed / skipped:")}
                  </Typography>
                  <Box sx={{ mt: 0.5, p: 1, bgcolor: "action.hover", borderRadius: 1, maxHeight: 140, overflow: "auto" }}>
                    {summary.failed.map((f) => (
                      <Typography key={f.path} variant="caption" sx={{ fontFamily: "monospace", display: "block", color: "error.main" }}>
                        ✗ {f.path} — {f.error}
                      </Typography>
                    ))}
                  </Box>
                </Box>
              )}
              {summary.tokens && (
                <Typography variant="caption" color="text.secondary">
                  {t("projects.app.gen.tokensSpent", "Tokens: {{i}} in / {{o}} out", {
                    i: summary.tokens.input || 0,
                    o: summary.tokens.output || 0,
                  })}
                </Typography>
              )}

              {/* Post-build LLM validation result + auto-fix loop status.
                  - Spinner while validation is running.
                  - Banner during auto-fix iterations (asking / writing /
                    rechecking) with a Stop button.
                  - ✓ or ⚠ alert + issue list when settled. */}
              <Divider />
              <Box>
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">
                    {t("projects.app.gen.validateTitle", "AI review")}
                  </Typography>
                  {autoFix.running && (
                    <Button
                      size="small"
                      color="warning"
                      startIcon={<Stop />}
                      onClick={stopAutoFix}
                    >
                      {t("projects.app.gen.stopAutoFix", "Stop auto-fix")}
                    </Button>
                  )}
                </Box>
                {autoFix.running ? (
                  <Alert severity="info" icon={<CircularProgress size={14} />}>
                    {t("projects.app.gen.autoFixStatus", "Auto-fix iteration {{n}}/{{max}}: {{status}}", {
                      n: autoFix.attempts,
                      max: AUTOFIX_MAX,
                      // Map known short statuses to translated strings;
                      // anything else (per-file progress like "3/5
                      // src/api.ts") gets passed through verbatim so the
                      // user sees real-time activity.
                      status: autoFix.status === "asking"
                        ? t("projects.app.gen.autoFixAsking", "asking the LLM for a fix plan…")
                        : autoFix.status === "rechecking"
                        ? t("projects.app.gen.autoFixRechecking", "re-checking…")
                        : autoFix.status
                          ? autoFix.status
                          : t("projects.app.gen.autoFixWorking", "working…"),
                    })}
                  </Alert>
                ) : validation.running ? (
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <CircularProgress size={14} />
                    <Typography variant="caption" color="text.secondary">
                      {t("projects.app.gen.validateRunning", "Reviewing the generated files…")}
                    </Typography>
                  </Box>
                ) : validation.result ? (
                  <Stack spacing={1}>
                    <Alert severity={validation.result.ok ? "success" : "warning"}>
                      {validation.result.summary || (validation.result.ok
                        ? t("projects.app.gen.validateOk", "Looks good — no issues found.")
                        : t("projects.app.gen.validateBad", "The reviewer flagged some issues."))}
                      {autoFix.attempts > 0 && (
                        <Typography variant="caption" sx={{ display: "block", mt: 0.5, opacity: 0.85 }}>
                          {validation.result.ok
                            ? t("projects.app.gen.autoFixSucceeded", "Resolved by auto-fix after {{n}} iteration(s).", { n: autoFix.attempts })
                            : autoFix.halted
                            ? t("projects.app.gen.autoFixHalted", "Auto-fix stopped at {{n}} iteration(s).", { n: autoFix.attempts })
                            : t("projects.app.gen.autoFixGaveUp", "Auto-fix tried {{n}} iteration(s) and didn't resolve everything — refine via chat or fix manually.", { n: autoFix.attempts })}
                        </Typography>
                      )}
                    </Alert>
                    {(validation.result.issues || []).length > 0 && (
                      <Box sx={{ p: 1, bgcolor: "action.hover", borderRadius: 1, maxHeight: 220, overflow: "auto" }}>
                        {validation.result.issues.map((issue, i) => (
                          <Box key={i} sx={{ mb: 0.75 }}>
                            <Typography
                              variant="caption"
                              sx={{
                                fontFamily: "monospace",
                                color: issue.severity === "high" ? "error.main"
                                  : issue.severity === "medium" ? "warning.main"
                                  : "text.secondary",
                              }}
                            >
                              [{issue.severity || "low"}] {issue.path}
                            </Typography>
                            <Typography variant="caption" sx={{ display: "block", pl: 2 }}>
                              {issue.message}
                            </Typography>
                          </Box>
                        ))}
                      </Box>
                    )}
                  </Stack>
                ) : (
                  <Typography variant="caption" color="text.disabled">
                    {t("projects.app.gen.validateSkipped", "Validation skipped.")}
                  </Typography>
                )}
              </Box>
            </Stack>
          </Box>
        )}
      </DialogContent>

      <DialogActions>
        {step === "executing" && (
          <Button color="warning" onClick={cancelExecute} startIcon={<Stop />}>
            {t("projects.app.gen.cancelBuild", "Cancel build")}
          </Button>
        )}
        {step === "done" && (
          <>
            <Button onClick={continueChat} startIcon={<Refresh />}>
              {t("projects.app.gen.continueChat", "Continue chat")}
            </Button>
            <Button variant="contained" onClick={closeAndReset}>
              {t("projects.app.gen.close", "Close")}
            </Button>
          </>
        )}
        {step === "chat" && (
          <Button onClick={onClose} disabled={streaming}>
            {t("projects.app.gen.close", "Close")}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
