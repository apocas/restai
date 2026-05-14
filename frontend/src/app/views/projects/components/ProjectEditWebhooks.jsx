import { useMemo, useState } from "react";
import {
  Alert, Box, Button, IconButton, Switch, Tab, Tabs, Tooltip, Typography,
} from "@mui/material";
import { OpenInNew, PlayArrow, Refresh, Visibility, VisibilityOff } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";
import {
  CopyButton, MonoField, SecretField, SectionHeader, StatusDot,
  dotSx, sectionLabelSx, sectionShellSx,
} from "./integrationsKit";

const ACCENT = "#0ea5e9";

const EVENTS = [
  {
    key: "budget_exceeded",
    accent: "#f59e0b",
    sample: {
      limit_eur: 50.0,
      spent_eur: 50.07,
      period: "monthly",
    },
  },
  {
    key: "sync_completed",
    accent: ACCENT,
    sample: {
      source_type: "url",
      source_id: "docs.example.com",
      documents: 12,
      chunks: 184,
      duration_ms: 4218,
    },
  },
  {
    key: "eval_completed",
    accent: "#8b5cf6",
    sample: {
      run_id: 17,
      dataset_id: 4,
      metrics: { answer_relevancy: 0.83, faithfulness: 0.91 },
      duration_ms: 12480,
    },
  },
  {
    key: "routine_failed",
    accent: "#f43f5e",
    sample: {
      routine_id: 3,
      routine_name: "daily-summary",
      error: "ConnectionError: HA unreachable",
    },
  },
];

// Mirrors restai/helper.py:_is_private_ip — purely cosmetic, server
// re-checks on delivery.
function classifyHost(rawUrl) {
  if (!rawUrl) return { state: "empty", label: "—" };
  let u;
  try { u = new URL(rawUrl); } catch { return { state: "bad", label: "invalid URL" }; }
  if (u.protocol !== "https:") return { state: "warn", label: "not HTTPS" };
  const host = u.hostname.toLowerCase();
  if (host === "localhost" || host === "0.0.0.0") return { state: "bad", label: "loopback" };
  const m = host.match(/^(\d+)\.(\d+)\.(\d+)\.(\d+)$/);
  if (m) {
    const [a, b] = [parseInt(m[1], 10), parseInt(m[2], 10)];
    if (a === 127) return { state: "bad", label: "loopback" };
    if (a === 10) return { state: "bad", label: "private IP" };
    if (a === 192 && b === 168) return { state: "bad", label: "private IP" };
    if (a === 172 && b >= 16 && b <= 31) return { state: "bad", label: "private IP" };
    if (a === 169 && b === 254) return { state: "bad", label: "link-local" };
  }
  return { state: "ok", label: "HTTPS · public" };
}

function parseEvents(csv) {
  if (!csv || !csv.trim()) return new Set(EVENTS.map((e) => e.key));
  return new Set(csv.replace(/;/g, ",").split(",").map((s) => s.trim()).filter(Boolean));
}
function joinEvents(set) {
  return EVENTS.map((e) => e.key).filter((k) => set.has(k)).join(", ");
}

function buildSamplePayload(eventKey, projectId, projectName) {
  const ev = EVENTS.find((e) => e.key === eventKey) || EVENTS[0];
  return {
    event: ev.key,
    project_id: projectId ?? 0,
    project_name: projectName ?? "your-project",
    fired_at: "2026-05-14T14:22:08.143Z",
    data: ev.sample,
  };
}

function buildSnippets(eventKey, url, projectId, projectName) {
  const body = JSON.stringify(buildSamplePayload(eventKey, projectId, projectName), null, 2);
  const headers = [
    "Content-Type: application/json",
    `X-RESTai-Event: ${eventKey}`,
    "X-RESTai-Signature: sha256=<hex digest of raw body>",
  ].join("\n");
  const py = `# Verify X-RESTai-Signature in your handler (Python)
import hmac, hashlib

SECRET = b"<your webhook_secret>"

def verify(raw_body: bytes, header: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    sent = header.split("=", 1)[1]
    digest = hmac.new(SECRET, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sent, digest)`;
  const node = `// Verify X-RESTai-Signature in your handler (Node)
const crypto = require("crypto");
const SECRET = "<your webhook_secret>";

function verify(rawBody, header) {
  if (!header || !header.startsWith("sha256=")) return false;
  const sent = header.slice("sha256=".length);
  const digest = crypto.createHmac("sha256", SECRET).update(rawBody).digest("hex");
  try {
    return crypto.timingSafeEqual(Buffer.from(sent, "hex"), Buffer.from(digest, "hex"));
  } catch { return false; }
}`;
  const curl = `curl -X POST '${url || "https://your-app.example.com/restai-events"}' \\
  -H 'Content-Type: application/json' \\
  -H 'X-RESTai-Event: ${eventKey}' \\
  -H 'X-RESTai-Signature: sha256=<hex>' \\
  --data-raw '${body.replace(/'/g, "'\\''")}'`;
  return { body, headers, py, node, curl };
}

export default function ProjectEditWebhooks({ state, setState, project }) {
  const { t } = useTranslation();
  const auth = useAuth();

  const url = state.options?.webhook_url || "";
  const secret = state.options?.webhook_secret || "";
  const subscribed = useMemo(() => parseEvents(state.options?.webhook_events || ""), [state.options?.webhook_events]);
  const allOn = subscribed.size === EVENTS.length;

  const [showSecret, setShowSecret] = useState(false);
  const [selected, setSelected] = useState(EVENTS[0].key);
  const [tab, setTab] = useState("body");
  const [testing, setTesting] = useState(false);
  const [rotating, setRotating] = useState(false);
  const [log, setLog] = useState([]);
  const [rotated, setRotated] = useState(null);

  const setOpt = (key, value) => setState({ ...state, options: { ...state.options, [key]: value } });

  const hostInfo = classifyHost(url);
  const isLive = !!url && hostInfo.state !== "empty" && hostInfo.state !== "bad";

  const toggleEvent = (key) => {
    const next = new Set(subscribed);
    if (next.has(key)) next.delete(key); else next.add(key);
    setOpt("webhook_events", next.size === EVENTS.length ? "" : joinEvents(next));
  };

  const fireTest = () => {
    if (!project?.id || !url) return;
    setTesting(true);
    api.post(`/projects/${project.id}/webhooks/test`, {}, auth.user.token)
      .then((res) => {
        const r = res.data || res;
        const status = r.ok ? "queued" : (String(r.reason || "").includes("private") || String(r.reason || "").includes("refused") ? "refused" : "filtered");
        setLog((prev) => [{ ts: new Date(), host: classifyHost(url).label, status, detail: r.reason || "synthetic `test` event" }, ...prev].slice(0, 10));
      })
      .catch((err) => {
        setLog((prev) => [{ ts: new Date(), host: classifyHost(url).label, status: "network", detail: err?.response?.data?.detail || err.message || "request failed" }, ...prev].slice(0, 10));
      })
      .finally(() => setTesting(false));
  };

  const rotateSecret = () => {
    if (!project?.id) return;
    setRotating(true);
    setRotated(null);
    api.post(`/projects/${project.id}/webhooks/rotate-secret`, {}, auth.user.token)
      .then((res) => {
        const r = res.data || res;
        if (r.secret) {
          setRotated(r.secret);
          setOpt("webhook_secret", r.secret);
          setShowSecret(true);
        }
      })
      .catch(() => {})
      .finally(() => setRotating(false));
  };

  const snippets = useMemo(() => buildSnippets(selected, url, project?.id, project?.name), [selected, url, project?.id, project?.name]);
  const tabContent = tab === "body" ? snippets.body
    : tab === "headers" ? snippets.headers
      : tab === "py" ? snippets.py
        : tab === "node" ? snippets.node
          : snippets.curl;

  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
        <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", letterSpacing: "0.18em", fontWeight: 700, textTransform: "uppercase" }}>
          {t("projects.edit.webhooks.title", "Event webhooks")}
        </Typography>
        <Box sx={{
          display: "inline-flex", alignItems: "center", gap: 0.6, px: 1, py: 0.35, borderRadius: 1,
          backgroundColor: isLive ? "rgba(16,185,129,0.10)" : "rgba(15,23,42,0.05)",
          border: `1px solid ${isLive ? "rgba(16,185,129,0.35)" : "rgba(15,23,42,0.10)"}`,
        }}>
          <Box sx={{ ...dotSx(isLive ? "#10b981" : "rgba(15,23,42,0.25)"), animation: isLive ? `${pulse} 2.6s ease-out infinite` : "none" }} />
          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", fontWeight: 700, color: isLive ? "#10b981" : "text.disabled", letterSpacing: "0.06em" }}>
            {isLive ? t("projects.edit.webhooks.live", "LIVE") : t("projects.edit.webhooks.off", "OFF")}
          </Typography>
        </Box>
        <Box sx={{ flex: 1 }} />
        <Typography sx={{ fontSize: "0.78rem", color: "text.secondary" }}>
          {t("projects.edit.webhooks.subtitle", "Outbound HTTPS notifications when project events fire.")}
        </Typography>
      </Box>

      {/* ── ENDPOINT ─────────────────────────────────────────────── */}
      <Box sx={sectionShellSx(ACCENT)}>
        <Box sx={{ p: 2.5, display: "flex", flexDirection: "column", gap: 2.25 }}>
          <Box sx={sectionLabelSx}>{t("projects.edit.webhooks.endpoint", "Endpoint")}</Box>

          <Box>
            <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.secondary", mb: 0.5, letterSpacing: "0.08em" }}>URL</Typography>
            <Box sx={{ display: "flex", gap: 1, alignItems: "stretch" }}>
              <Box
                component="input"
                value={url}
                onChange={(e) => setOpt("webhook_url", e.target.value)}
                placeholder="https://hooks.mysite.com/restai-events"
                spellCheck={false}
                sx={{
                  flex: 1, minWidth: 0,
                  fontFamily: FONT_MONO, fontSize: "0.85rem",
                  px: 1.25, py: 1,
                  borderRadius: 1.25,
                  border: "1px solid rgba(15,23,42,0.14)",
                  backgroundColor: "#fafbfc",
                  color: "text.primary",
                  outline: "none",
                  transition: "border-color .15s ease, box-shadow .15s ease",
                  "&:focus": { borderColor: ACCENT, boxShadow: `0 0 0 3px ${ACCENT}22` },
                }}
              />
              <Box sx={{
                display: "flex", alignItems: "center", gap: 0.75, px: 1, borderRadius: 1.25,
                border: `1px solid ${hostInfo.state === "ok" ? "rgba(16,185,129,0.35)" : hostInfo.state === "bad" ? "rgba(239,68,68,0.35)" : hostInfo.state === "warn" ? "rgba(245,158,11,0.35)" : "rgba(15,23,42,0.10)"}`,
                backgroundColor: hostInfo.state === "ok" ? "rgba(16,185,129,0.06)" : hostInfo.state === "bad" ? "rgba(239,68,68,0.06)" : hostInfo.state === "warn" ? "rgba(245,158,11,0.06)" : "transparent",
              }}>
                <StatusDot state={hostInfo.state} />
                <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", fontWeight: 700, color: hostInfo.state === "ok" ? "#047857" : hostInfo.state === "bad" ? "#b91c1c" : hostInfo.state === "warn" ? "#92400e" : "text.disabled", whiteSpace: "nowrap" }}>
                  {hostInfo.label}
                </Typography>
              </Box>
            </Box>
            <Typography sx={{ fontSize: "0.7rem", color: "text.disabled", mt: 0.5 }}>
              {t("projects.edit.webhooks.urlHelp", "HTTPS only · private/RFC1918 hosts refused at delivery time.")}
            </Typography>
          </Box>

          <Box>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.secondary", letterSpacing: "0.08em", flex: 1 }}>SIGNING SECRET</Typography>
              {secret && (
                <Box sx={{
                  display: "inline-flex", alignItems: "center", gap: 0.5, px: 0.75, py: 0.15, borderRadius: 0.75,
                  backgroundColor: "rgba(16,185,129,0.10)", border: "1px solid rgba(16,185,129,0.30)",
                }}>
                  <Box sx={dotSx("#10b981")} />
                  <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", fontWeight: 700, color: "#047857", letterSpacing: "0.06em" }}>SIGNING ON</Typography>
                </Box>
              )}
            </Box>
            <Box sx={{ display: "flex", gap: 1, alignItems: "stretch" }}>
              <Box
                component="input"
                type={showSecret ? "text" : "password"}
                value={secret}
                onChange={(e) => setOpt("webhook_secret", e.target.value)}
                placeholder="(none — leave empty to skip signing)"
                spellCheck={false}
                sx={{
                  flex: 1, minWidth: 0,
                  fontFamily: FONT_MONO, fontSize: "0.85rem",
                  px: 1.25, py: 1,
                  borderRadius: 1.25,
                  border: "1px solid rgba(15,23,42,0.14)",
                  backgroundColor: "#fafbfc",
                  color: "text.primary",
                  outline: "none",
                  "&:focus": { borderColor: ACCENT, boxShadow: `0 0 0 3px ${ACCENT}22` },
                }}
              />
              <IconButton size="small" onClick={() => setShowSecret((v) => !v)} sx={{ border: "1px solid rgba(15,23,42,0.10)", borderRadius: 1.25 }}>
                {showSecret ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
              </IconButton>
              <Tooltip title={t("projects.edit.webhooks.rotateTip", "Mint fresh 32-byte secret · prior receivers will need the new value")} arrow>
                <span>
                  <Button
                    onClick={rotateSecret}
                    disabled={!project?.id || rotating}
                    startIcon={<Refresh sx={{ fontSize: 16 }} />}
                    sx={{
                      fontFamily: FONT_MONO, fontSize: "0.7rem", letterSpacing: "0.08em",
                      px: 1.25, borderRadius: 1.25, minWidth: 0,
                      color: ACCENT, border: `1px solid ${ACCENT}55`,
                      "&:hover": { backgroundColor: `${ACCENT}11`, borderColor: ACCENT },
                    }}
                  >
                    {rotating ? "rotating…" : t("projects.edit.webhooks.rotate", "rotate")}
                  </Button>
                </span>
              </Tooltip>
            </Box>
            <Typography sx={{ fontSize: "0.7rem", color: "text.disabled", mt: 0.5 }}>
              {t("projects.edit.webhooks.secretHelp", "HMAC-SHA256 of body, sent in X-RESTai-Signature. Encrypted at rest.")}
            </Typography>
            {rotated && (
              <Alert severity="warning" sx={{ mt: 1, fontFamily: FONT_MONO, fontSize: "0.78rem" }}>
                {t("projects.edit.webhooks.rotateWarn", "New secret minted. Capture it now — the masked form will hide it after the next page reload. Existing receivers must update before the next event fires.")}
              </Alert>
            )}
          </Box>
        </Box>
      </Box>

      {/* ── SUBSCRIPTIONS ────────────────────────────────────────── */}
      <Box sx={sectionShellSx(ACCENT)}>
        <Box sx={{ p: 2.5, display: "flex", flexDirection: "column", gap: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
            <Box sx={sectionLabelSx}>{t("projects.edit.webhooks.subscriptions", "Subscriptions")}</Box>
            <Box sx={{ flex: 1 }} />
            <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", color: "text.disabled", letterSpacing: "0.06em" }}>
              {subscribed.size} / {EVENTS.length} {t("projects.edit.webhooks.events", "events")}{allOn ? ` · ${t("projects.edit.webhooks.allDefault", "all (default)")}` : ""}
            </Typography>
          </Box>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 1.25 }}>
            {EVENTS.map((ev) => {
              const on = subscribed.has(ev.key);
              const isSel = selected === ev.key;
              return (
                <Box
                  key={ev.key}
                  onClick={() => setSelected(ev.key)}
                  sx={{
                    position: "relative",
                    p: 1.5, pl: 2.25,
                    borderRadius: 1.5,
                    border: `1px solid ${isSel ? `${ACCENT}66` : "rgba(15,23,42,0.10)"}`,
                    backgroundColor: isSel ? `${ACCENT}06` : "#fafbfc",
                    cursor: "pointer",
                    transition: "border-color .15s ease, background-color .15s ease",
                    "&:hover": { borderColor: `${ACCENT}55` },
                    "&::before": {
                      content: '""', position: "absolute",
                      left: 0, top: 0, bottom: 0, width: 4,
                      background: ev.accent,
                      opacity: on ? 1 : 0.3,
                      borderRadius: "1.5px 0 0 1.5px",
                    },
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                        <Box sx={dotSx(ev.accent)} />
                        <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", fontWeight: 700, color: "text.primary" }}>
                          {ev.key}
                        </Typography>
                      </Box>
                      <Typography sx={{ mt: 0.5, fontSize: "0.74rem", color: "text.secondary", lineHeight: 1.45 }}>
                        {t(`projects.edit.webhooks.event.${ev.key}`, defaultEventDescription(ev.key))}
                      </Typography>
                    </Box>
                    <Switch
                      size="small"
                      checked={on}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => toggleEvent(ev.key)}
                      sx={{
                        "& .MuiSwitch-switchBase.Mui-checked": { color: ev.accent },
                        "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": { backgroundColor: ev.accent },
                      }}
                    />
                  </Box>
                </Box>
              );
            })}
          </Box>
        </Box>
      </Box>

      {/* ── PAYLOAD INSPECTOR ────────────────────────────────────── */}
      <Box sx={{
        borderRadius: 2,
        overflow: "hidden",
        border: "1px solid rgba(15,23,42,0.08)",
        backgroundColor: "#0b1220",
        boxShadow: "0 6px 18px rgba(15,23,42,0.16)",
      }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 0.85, borderBottom: "1px solid rgba(255,255,255,0.06)", backgroundColor: "rgba(255,255,255,0.02)" }}>
          <Box sx={{ display: "flex", gap: 0.6 }}>
            {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
              <Box key={c} sx={{ width: 10, height: 10, borderRadius: "50%", backgroundColor: c, opacity: 0.85 }} />
            ))}
          </Box>
          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "#7dd3fc", letterSpacing: "0.18em", textTransform: "uppercase", fontWeight: 700, ml: 0.5 }}>
            {t("projects.edit.webhooks.inspector", "Payload inspector")}
          </Typography>
          <Box sx={{ flex: 1 }} />
          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", color: "#cbd5e1" }}>
            ●●● <Box component="span" sx={{ color: "#7dd3fc", fontWeight: 700 }}>{selected}</Box>
          </Typography>
          <CopyButton value={tabContent} />
        </Box>
        <Tabs
          value={tab}
          onChange={(_, v) => setTab(v)}
          variant="scrollable"
          scrollButtons={false}
          sx={{
            minHeight: 32,
            backgroundColor: "rgba(255,255,255,0.02)",
            borderBottom: "1px solid rgba(255,255,255,0.04)",
            "& .MuiTab-root": {
              minHeight: 32, py: 0,
              fontFamily: FONT_MONO, fontSize: "0.66rem",
              letterSpacing: "0.14em", textTransform: "uppercase",
              color: "#94a3b8", fontWeight: 700,
            },
            "& .Mui-selected": { color: "#7dd3fc !important" },
            "& .MuiTabs-indicator": { backgroundColor: "#7dd3fc" },
          }}
        >
          <Tab value="body" label="Body" />
          <Tab value="headers" label="Headers" />
          <Tab value="py" label="Verify · Python" />
          <Tab value="node" label="Verify · Node" />
          <Tab value="curl" label="cURL" />
        </Tabs>
        <Box component="pre" sx={{
          margin: 0, padding: "14px 18px",
          fontFamily: FONT_MONO, fontSize: "0.78rem",
          lineHeight: 1.6, color: "#cbd5e1",
          whiteSpace: "pre-wrap", wordBreak: "break-word",
          maxHeight: 360, overflow: "auto",
        }}>
          {tabContent}
        </Box>
      </Box>

      {/* ── TEST CONSOLE ─────────────────────────────────────────── */}
      <Box sx={sectionShellSx(ACCENT)}>
        <Box sx={{ p: 2.5, display: "flex", flexDirection: "column", gap: 1.5 }}>
          <Box sx={sectionLabelSx}>{t("projects.edit.webhooks.testConsole", "Test console")}</Box>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
            <Button
              variant="outlined"
              onClick={fireTest}
              disabled={!project?.id || !url || testing}
              startIcon={<PlayArrow />}
            >
              {testing ? t("projects.edit.webhooks.firing", "Firing…") : t("projects.edit.webhooks.fireTest", "Fire test event")}
            </Button>
            {!url && (
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", color: "text.disabled" }}>
                {t("projects.edit.webhooks.fireDisabled", "set a URL above to enable")}
              </Typography>
            )}
            <Box sx={{ flex: 1 }} />
            {log.length > 0 && (
              <Button onClick={() => setLog([])} size="small" sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.disabled" }}>
                {t("projects.edit.webhooks.clearLog", "clear log")}
              </Button>
            )}
          </Box>
          <Box sx={{
            borderRadius: 1.5, p: 1.5, minHeight: 70,
            backgroundColor: "#0b1220",
            fontFamily: FONT_MONO, fontSize: "0.75rem", color: "#cbd5e1",
            border: "1px solid rgba(15,23,42,0.10)",
          }}>
            {log.length === 0 ? (
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.74rem", color: "#475569", fontStyle: "italic" }}>
                {t("projects.edit.webhooks.logEmpty", "no test fires yet — fire one to see the receiver result")}
              </Typography>
            ) : log.map((entry, i) => {
              const palette = {
                queued:   { color: "#10b981", label: "queued" },
                filtered: { color: "#f59e0b", label: "FILTERED" },
                refused:  { color: "#ef4444", label: "REFUSED" },
                network:  { color: "#ef4444", label: "NETWORK" },
              }[entry.status] || { color: "#cbd5e1", label: entry.status };
              const ts = entry.ts.toTimeString().slice(0, 8);
              return (
                <Box key={i} sx={{ display: "flex", alignItems: "baseline", gap: 1, py: 0.25, opacity: i === 0 ? 1 : 0.7 }}>
                  <Box component="span" sx={{ color: "#64748b" }}>[{ts}]</Box>
                  <Box component="span" sx={{ color: "#94a3b8" }}>POST →</Box>
                  <Box component="span" sx={{ color: "#cbd5e1" }}>{entry.host}</Box>
                  <Box component="span" sx={{ color: palette.color, fontWeight: 700 }}>{palette.label}</Box>
                  <Box component="span" sx={{ color: "#64748b", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    · {entry.detail}
                  </Box>
                </Box>
              );
            })}
          </Box>
          <Typography sx={{ fontSize: "0.7rem", color: "text.disabled", display: "flex", alignItems: "center", gap: 0.5 }}>
            <OpenInNew sx={{ fontSize: 12 }} />
            {t("projects.edit.webhooks.logFootnote", "Fire-and-forget · 10 s timeout · backend doesn't surface receiver response. Check your receiver's own log to confirm 2xx.")}
          </Typography>
        </Box>
      </Box>
    </Box>
  );
}

function defaultEventDescription(key) {
  switch (key) {
    case "budget_exceeded": return "Project hit its budget cap. Fired BEFORE the 402 to the caller.";
    case "sync_completed":  return "Knowledge-base sync source finished (URL/S3/Drive/Confluence/SharePoint). One event per source per run.";
    case "eval_completed":  return "Eval run finished — score + per-metric breakdown in the payload.";
    case "routine_failed":  return "A scheduled routine raised on its tick. Body carries the exception summary.";
    default: return "";
  }
}
