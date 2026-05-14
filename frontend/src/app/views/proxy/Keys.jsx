import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, CircularProgress, Divider,
  IconButton, MenuItem, Stack, styled, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Tooltip, Typography,
  Autocomplete, Alert, Dialog, DialogActions, DialogContent, DialogTitle,
} from "@mui/material";
import RouteIcon from "@mui/icons-material/Route";
import KeyIcon from "@mui/icons-material/VpnKey";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import CheckIcon from "@mui/icons-material/Check";
import CodeIcon from "@mui/icons-material/Code";
import BoltIcon from "@mui/icons-material/Bolt";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";

import PageHero from "app/components/page/PageHero";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Page accent — LiteLLM proxy is the "router" between callers and
// model providers. Cyan reads as wire / routing. Distinct from the
// other modernized pages.
const ACCENT = "#0891b2";
const ACCENT_SOFT = "rgba(8,145,178,0.10)";

// ── Tile card with accent rail and hover sweep — same vocabulary as
// the project library cards.
const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  marginBottom: 24,
  transition: "border-color 0.25s ease, box-shadow 0.25s ease, transform 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    pointerEvents: "none",
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

const TileHeader = ({ icon, title, subtitle, accent = ACCENT, action }) => (
  <Box
    sx={{
      px: 3, pt: 2.75, pb: 2,
      display: "flex",
      alignItems: "center",
      gap: 1.75,
      borderBottom: "1px solid rgba(15,23,42,0.06)",
    }}
  >
    <Box
      sx={{
        width: 40, height: 40,
        flexShrink: 0,
        borderRadius: 1.5,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        background: `${accent}1a`,
        color: accent,
        "& svg": { fontSize: 22 },
      }}
    >
      {icon}
    </Box>
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
        {title}
      </Typography>
      {subtitle && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
          {subtitle}
        </Typography>
      )}
    </Box>
    {action}
  </Box>
);

// ── Mini "BASE URL" strip — terminal-aesthetic banner with a copy
// button. Same look as the DirectAccess page so admins recognise it.
function ConsoleStrip({ label, value, accent = ACCENT, mono = true }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(value);
    setCopied(true);
    toast.success("Copied");
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <Box
      sx={{
        borderRadius: 2.5,
        backgroundColor: "#0b1220",
        color: "#cbd5e1",
        p: 1.5,
        pl: 2,
        display: "flex",
        alignItems: "center",
        gap: 2,
        flexWrap: "wrap",
        border: "1px solid rgba(15,23,42,0.12)",
        boxShadow: "0 8px 22px rgba(15,23,42,0.10)",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, minWidth: 0 }}>
        <Box
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.65rem",
            letterSpacing: "0.18em",
            fontWeight: 700,
            color: accent,
          }}
        >
          {label}
        </Box>
        <Box
          component="code"
          sx={{
            fontFamily: mono ? FONT_MONO : undefined,
            fontSize: "0.85rem",
            color: "#fff",
            wordBreak: "break-all",
          }}
        >
          {value}
        </Box>
      </Box>
      <Tooltip title={copied ? "Copied" : "Copy"}>
        <IconButton
          size="small"
          onClick={handleCopy}
          sx={{
            color: copied ? "#28c840" : "rgba(255,255,255,0.7)",
            border: "1px solid rgba(255,255,255,0.12)",
            borderRadius: 1.5,
            "&:hover": { color: "#fff", backgroundColor: "rgba(255,255,255,0.08)" },
          }}
        >
          {copied ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
        </IconButton>
      </Tooltip>
    </Box>
  );
}

// ── Terminal-style code block: dark slate background, traffic-light
// dots, language label, copy button. Lifted from DirectAccess.
function CodeTerminal({ language, code }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <Box
      sx={{
        borderRadius: 2,
        overflow: "hidden",
        border: "1px solid rgba(15,23,42,0.08)",
        backgroundColor: "#0b1220",
        boxShadow: "0 8px 22px rgba(15,23,42,0.18)",
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          gap: 1,
          px: 1.5, py: 1,
          borderBottom: "1px solid rgba(255,255,255,0.06)",
          backgroundColor: "rgba(255,255,255,0.02)",
        }}
      >
        <Box sx={{ display: "flex", gap: 0.6, mr: 1 }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
            <Box
              key={c}
              sx={{ width: 11, height: 11, borderRadius: "50%", backgroundColor: c, opacity: 0.85 }}
            />
          ))}
        </Box>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            color: "rgba(255,255,255,0.55)",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            fontWeight: 600,
            flex: 1,
          }}
        >
          {language}
        </Typography>
        <Tooltip title={copied ? "Copied" : "Copy"}>
          <IconButton
            size="small"
            onClick={handleCopy}
            sx={{
              color: copied ? "#28c840" : "rgba(255,255,255,0.55)",
              "&:hover": { color: "#fff", backgroundColor: "rgba(255,255,255,0.08)" },
            }}
          >
            {copied ? <CheckIcon fontSize="small" /> : <ContentCopyIcon fontSize="small" />}
          </IconButton>
        </Tooltip>
      </Box>
      <Box
        component="pre"
        sx={{
          margin: 0,
          padding: "16px 20px",
          fontFamily: FONT_MONO,
          fontSize: "0.78rem",
          lineHeight: 1.65,
          color: "#cbd5e1",
          overflowX: "auto",
          tabSize: 4,
          background:
            "linear-gradient(180deg, rgba(255,255,255,0) 70%, rgba(56,189,248,0.04))",
        }}
      >
        <code>{code}</code>
      </Box>
    </Box>
  );
}

// ── Spend / budget gauge — segmented bar with cyan→amber→red as the
// gauge fills. When there's no budget set, renders a flat spend pill.
function SpendGauge({ spend, budget }) {
  const s = Number(spend) || 0;
  if (!budget || budget <= 0) {
    return (
      <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
        <Box
          component="span"
          sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", fontWeight: 600 }}
        >
          {s.toFixed(3)}
        </Box>
        <Box component="span" sx={{ fontSize: "0.7rem", color: "text.disabled" }}>€</Box>
      </Box>
    );
  }
  const ratio = Math.min(1, s / Number(budget));
  const pct = ratio * 100;
  const color = ratio >= 0.9 ? "#ef4444" : ratio >= 0.7 ? "#f59e0b" : ACCENT;
  return (
    <Box sx={{ minWidth: 130 }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          mb: 0.5,
        }}
      >
        <Box
          component="span"
          sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", fontWeight: 600, color }}
        >
          {s.toFixed(3)}
        </Box>
        <Box
          component="span"
          sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.disabled" }}
        >
          / {Number(budget).toFixed(2)} €
        </Box>
      </Box>
      <Box
        sx={{
          position: "relative",
          height: 5,
          borderRadius: 3,
          backgroundColor: "rgba(15,23,42,0.06)",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            position: "absolute",
            left: 0, top: 0, bottom: 0,
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
            borderRadius: 3,
          }}
        />
      </Box>
    </Box>
  );
}

export default function Proxy() {
  const { t } = useTranslation();
  const auth = useAuth();
  const { platformCapabilities } = usePlatformCapabilities();

  const DURATIONS = [
    { value: "", label: t("proxy.durations.none") },
    { value: "1h", label: t("proxy.durations.hourly") },
    { value: "1d", label: t("proxy.durations.daily") },
    { value: "7d", label: t("proxy.durations.weekly") },
    { value: "30d", label: t("proxy.durations.monthly") },
  ];
  const [keys, setKeys] = useState([]);
  const [info, setInfo] = useState({ models: [], url: "" });
  const [loading, setLoading] = useState(true);

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState(null);
  const [keyCopied, setKeyCopied] = useState(false);
  const [form, setForm] = useState({
    name: "", models: [],
    max_budget: "", duration_budget: "", rpm: "", tpm: "",
  });

  const fetchAll = () => {
    setLoading(true);
    return Promise.all([
      api.get("/proxy/keys", auth.user.token).then((d) => setKeys(d.keys || [])).catch(() => {}),
      api.get("/proxy/info", auth.user.token).then((d) => setInfo(d || { models: [], url: "" })).catch(() => {}),
    ]).finally(() => setLoading(false));
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("proxy.title");
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const handleDelete = (key_id, name) => {
    if (name === "default") {
      toast.error(t("proxy.cannotDeleteDefault"));
      return;
    }
    if (!window.confirm(t("proxy.deleteConfirm", { name }))) return;
    api.delete("/proxy/keys/" + key_id, auth.user.token)
      .then(() => { toast.success(t("proxy.keyDeleted")); fetchAll(); })
      .catch(() => {});
  };

  const openDialog = () => {
    setForm({ name: "", models: [], max_budget: "", duration_budget: "", rpm: "", tpm: "" });
    setCreatedKey(null);
    setKeyCopied(false);
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setCreatedKey(null);
    setKeyCopied(false);
  };

  const handleCreate = () => {
    if (!form.name.trim()) { toast.error(t("proxy.nameRequired")); return; }
    if (!form.models || form.models.length === 0) { toast.error(t("proxy.modelRequired")); return; }

    setCreating(true);
    const payload = {
      name: form.name.trim(),
      models: form.models,
      max_budget: form.max_budget ? Number(form.max_budget) : null,
      duration_budget: form.duration_budget || null,
      rpm: form.rpm ? Number(form.rpm) : null,
      tpm: form.tpm ? Number(form.tpm) : null,
    };
    api.post("/proxy/keys", payload, auth.user.token)
      .then((response) => {
        toast.success(t("proxy.created"));
        setCreatedKey(response.key);
        fetchAll();
      })
      .catch(() => {})
      .finally(() => setCreating(false));
  };

  const copyCreatedKey = () => {
    if (!createdKey) return;
    navigator.clipboard.writeText(createdKey);
    setKeyCopied(true);
    toast.success(t("common.copied"));
  };

  const proxyUrl = platformCapabilities?.proxy_url || info.url || "127.0.0.1";
  const totalSpend = keys.reduce((acc, k) => acc + (Number(k.spend) || 0), 0);

  const usageCode = `from openai import OpenAI

client = OpenAI(
    api_key="YOUR_KEY",
    base_url="${proxyUrl}",
)

response = client.chat.completions.create(
    model="${(info.models && info.models[0]) || "model-name"}",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response)`;

  return (
    <Container>
      <PageHero
        icon={<RouteIcon sx={{ color: "#fff" }} />}
        eyebrow="LITELLM PROXY"
        title={t("proxy.title") || "AI Proxy"}
        subtitle="OpenAI-compatible router across 100+ providers. Mint scoped keys with budgets, rate limits and per-model allowlists — every request flows through the proxy and is metered."
        showStatusDot
        statusLabel="Live"
        stats={[
          { glyph: "◆", color: "#7dd3fc", label: `${info.models.length} model${info.models.length === 1 ? "" : "s"}` },
          { glyph: "★", color: "#a7f3d0", label: `${keys.length} active key${keys.length === 1 ? "" : "s"}` },
          { glyph: "Σ", color: "#fcd34d", label: `${totalSpend.toFixed(2)} € total spend` },
        ]}
      />

      {/* Base URL strip + available models */}
      <Box sx={{ mb: 3 }}>
        <ConsoleStrip
          label="BASE URL"
          value={proxyUrl}
          accent="#7dd3fc"
        />
        <Box sx={{ mt: 2, display: "flex", flexWrap: "wrap", gap: 0.75, alignItems: "center" }}>
          <Typography
            variant="overline"
            sx={{
              color: "text.secondary",
              fontWeight: 600,
              letterSpacing: 1.2,
              fontSize: "0.65rem",
              mr: 0.5,
            }}
          >
            {t("proxy.availableModels", { count: info.models.length })}
          </Typography>
          {info.models.length === 0 ? (
            <Typography variant="caption" color="text.secondary" sx={{ fontStyle: "italic" }}>
              {t("proxy.noModels")}
            </Typography>
          ) : (
            info.models.map((model) => (
              <Chip
                key={model}
                label={model}
                size="small"
                sx={{
                  height: 22,
                  fontSize: "0.7rem",
                  fontFamily: FONT_MONO,
                  fontWeight: 500,
                  color: ACCENT,
                  backgroundColor: ACCENT_SOFT,
                  border: `1px solid ${ACCENT}33`,
                  "& .MuiChip-label": { px: 1 },
                }}
              />
            ))
          )}
        </Box>
      </Box>

      <TileCard elevation={0} accent={ACCENT}>
        <TileHeader
          icon={<KeyIcon />}
          title={t("proxy.apiKeys") || "API Keys"}
          subtitle={t("proxy.keys", { count: keys.length })}
          accent={ACCENT}
          action={
            <Button
              variant="contained"
              size="small"
              startIcon={<AddIcon />}
              onClick={openDialog}
              sx={{
                textTransform: "none",
                fontWeight: 600,
                background: `linear-gradient(135deg, ${ACCENT} 0%, #0e7490 100%)`,
                boxShadow: `0 4px 14px ${ACCENT}55`,
                "&:hover": {
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #155e75 100%)`,
                  boxShadow: `0 6px 18px ${ACCENT}77`,
                },
              }}
            >
              {t("proxy.newKey")}
            </Button>
          }
        />

        <Table size="small">
          <TableHead>
            <TableRow sx={{ "& th": { backgroundColor: "rgba(15,23,42,0.02)", fontWeight: 600 } }}>
              <TableCell sx={{ pl: 3 }}>{t("proxy.columns.name")}</TableCell>
              <TableCell>{t("proxy.columns.key")}</TableCell>
              <TableCell>{t("proxy.columns.models")}</TableCell>
              <TableCell>{t("proxy.columns.spend")}</TableCell>
              <TableCell>{t("proxy.columns.duration")}</TableCell>
              <TableCell align="right">{t("proxy.columns.rpm")}</TableCell>
              <TableCell align="right">{t("proxy.columns.tpm")}</TableCell>
              <TableCell align="center" sx={{ pr: 3 }}>{t("proxy.columns.actions")}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 5 }}>
                  <CircularProgress size={24} sx={{ color: ACCENT }} />
                </TableCell>
              </TableRow>
            ) : keys.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} align="center" sx={{ py: 6 }}>
                  <Box
                    sx={{
                      display: "inline-flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: 1.25,
                    }}
                  >
                    <Box
                      sx={{
                        width: 56,
                        height: 56,
                        borderRadius: "50%",
                        background: ACCENT_SOFT,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      <KeyIcon sx={{ fontSize: 28, color: ACCENT }} />
                    </Box>
                    <Typography variant="body2" color="text.secondary">
                      {t("proxy.noKeys")}
                    </Typography>
                  </Box>
                </TableCell>
              </TableRow>
            ) : (
              keys.map((k) => {
                const isDefault = k.name === "default";
                return (
                  <TableRow
                    key={k.id}
                    sx={{
                      "&:hover": { backgroundColor: "rgba(15,23,42,0.025)" },
                      transition: "background-color 0.15s ease",
                    }}
                  >
                    <TableCell sx={{ pl: 3, py: 1.5 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                        <Typography sx={{ fontWeight: 600, fontSize: "0.85rem" }}>
                          {k.name || "—"}
                        </Typography>
                        {isDefault && (
                          <Chip
                            label="default"
                            size="small"
                            sx={{
                              height: 18,
                              fontSize: "0.6rem",
                              fontWeight: 600,
                              fontFamily: FONT_MONO,
                              backgroundColor: ACCENT_SOFT,
                              color: ACCENT,
                              "& .MuiChip-label": { px: 0.75 },
                            }}
                          />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box
                        component="code"
                        sx={{
                          fontFamily: FONT_MONO,
                          fontSize: "0.72rem",
                          color: "text.secondary",
                          backgroundColor: "rgba(15,23,42,0.04)",
                          px: 0.75,
                          py: 0.25,
                          borderRadius: 0.75,
                        }}
                      >
                        {k.key}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, maxWidth: 240 }}>
                        {(k.models || []).slice(0, 3).map((m, i) => (
                          <Chip
                            key={i}
                            label={m}
                            size="small"
                            sx={{
                              height: 20,
                              fontSize: "0.68rem",
                              fontFamily: FONT_MONO,
                              backgroundColor: ACCENT_SOFT,
                              color: ACCENT,
                              border: `1px solid ${ACCENT}33`,
                              "& .MuiChip-label": { px: 0.75 },
                            }}
                          />
                        ))}
                        {(k.models || []).length > 3 && (
                          <Tooltip title={k.models.slice(3).join(", ")}>
                            <Chip
                              label={`+${k.models.length - 3}`}
                              size="small"
                              sx={{
                                height: 20,
                                fontSize: "0.68rem",
                                fontWeight: 600,
                                "& .MuiChip-label": { px: 0.75 },
                              }}
                            />
                          </Tooltip>
                        )}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <SpendGauge spend={k.spend} budget={k.max_budget} />
                    </TableCell>
                    <TableCell>
                      {k.duration_budget ? (
                        <Box
                          component="span"
                          sx={{
                            fontFamily: FONT_MONO,
                            fontSize: "0.72rem",
                            color: "text.secondary",
                          }}
                        >
                          {k.duration_budget}
                        </Box>
                      ) : "—"}
                    </TableCell>
                    <TableCell align="right">
                      <Box
                        component="span"
                        sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", color: k.rpm ? "text.primary" : "text.disabled" }}
                      >
                        {k.rpm || "—"}
                      </Box>
                    </TableCell>
                    <TableCell align="right">
                      <Box
                        component="span"
                        sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", color: k.tpm ? "text.primary" : "text.disabled" }}
                      >
                        {k.tpm || "—"}
                      </Box>
                    </TableCell>
                    <TableCell align="center" sx={{ pr: 3 }}>
                      <Tooltip title={isDefault ? t("proxy.cannotDeleteDefault") : t("proxy.deleteTip")}>
                        <span>
                          <IconButton
                            size="small"
                            onClick={() => handleDelete(k.id, k.name)}
                            disabled={isDefault}
                            sx={{
                              color: "text.disabled",
                              "&:hover": { color: "#ef4444", backgroundColor: "rgba(239,68,68,0.08)" },
                            }}
                          >
                            <DeleteIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TileCard>

      <TileCard elevation={0} accent={ACCENT}>
        <TileHeader
          icon={<CodeIcon />}
          title={t("proxy.usageExample") || "Usage example"}
          subtitle="OpenAI-compatible — point any SDK at the proxy URL with your minted key."
          accent={ACCENT}
        />
        <Box sx={{ p: 2.5 }}>
          <CodeTerminal language="Python · OpenAI SDK" code={usageCode} />
        </Box>
      </TileCard>

      {/* ── New Key Dialog ─────────────────────────────────── */}
      <Dialog
        open={dialogOpen}
        onClose={closeDialog}
        maxWidth="sm"
        fullWidth
        PaperProps={{
          sx: {
            borderRadius: 3,
            overflow: "hidden",
          },
        }}
      >
        {/* Coloured accent rail at top of dialog */}
        <Box
          sx={{
            position: "relative",
            height: 4,
            background: `linear-gradient(90deg, ${ACCENT}, #0e7490, ${ACCENT})`,
          }}
        />

        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 2 }}>
          <Box
            sx={{
              width: 36, height: 36,
              borderRadius: 1.5,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              background: ACCENT_SOFT,
              color: ACCENT,
            }}
          >
            {createdKey ? <CheckIcon /> : <AddIcon />}
          </Box>
          <Box sx={{ flex: 1 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.2 }}>
              {createdKey ? "Key created" : t("proxy.createTitle")}
            </Typography>
            {!createdKey && (
              <Typography variant="caption" color="text.secondary">
                Mint a scoped key with budget, rate limits and an allowlist.
              </Typography>
            )}
          </Box>
        </DialogTitle>
        <Divider />
        <DialogContent sx={{ pt: 3 }}>
          {createdKey ? (
            <Stack spacing={2.5}>
              <Alert
                severity="warning"
                variant="outlined"
                icon={<BoltIcon />}
                sx={{
                  borderColor: "#f59e0b",
                  backgroundColor: "rgba(245,158,11,0.06)",
                  alignItems: "center",
                }}
              >
                <strong>One-time reveal.</strong> Copy this key now — it can't be shown again.
              </Alert>

              <Box
                sx={{
                  position: "relative",
                  borderRadius: 2.5,
                  border: `1px solid ${ACCENT}33`,
                  background: "linear-gradient(135deg, #0b1220 0%, #0e1c2e 100%)",
                  overflow: "hidden",
                  // Subtle pulse halo to draw the eye to the key
                  "&::before": {
                    content: '""',
                    position: "absolute",
                    inset: -2,
                    borderRadius: 2.5,
                    border: `1px solid ${ACCENT}55`,
                    animation: `${pulse} 2.4s ease-out infinite`,
                    pointerEvents: "none",
                  },
                }}
              >
                <Box
                  sx={{
                    px: 2,
                    py: 1,
                    borderBottom: "1px solid rgba(255,255,255,0.08)",
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                  }}
                >
                  <Box sx={{ display: "flex", gap: 0.6 }}>
                    {["#ff5f57", "#febc2e", "#28c840"].map((c) => (
                      <Box
                        key={c}
                        sx={{
                          width: 10, height: 10, borderRadius: "50%",
                          backgroundColor: c, opacity: 0.85,
                        }}
                      />
                    ))}
                  </Box>
                  <Typography
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.65rem",
                      letterSpacing: "0.18em",
                      fontWeight: 700,
                      color: ACCENT,
                      flex: 1,
                    }}
                  >
                    YOUR_KEY
                  </Typography>
                </Box>
                <Box
                  component="code"
                  sx={{
                    display: "block",
                    p: 2.25,
                    fontFamily: FONT_MONO,
                    fontSize: "0.95rem",
                    color: "#fff",
                    wordBreak: "break-all",
                    lineHeight: 1.55,
                  }}
                >
                  {createdKey}
                </Box>
              </Box>

              <Button
                variant="contained"
                size="large"
                fullWidth
                startIcon={keyCopied ? <CheckIcon /> : <ContentCopyIcon />}
                onClick={copyCreatedKey}
                sx={{
                  textTransform: "none",
                  fontWeight: 700,
                  py: 1.25,
                  background: keyCopied
                    ? "linear-gradient(135deg, #10b981 0%, #059669 100%)"
                    : `linear-gradient(135deg, ${ACCENT} 0%, #0e7490 100%)`,
                  boxShadow: keyCopied
                    ? "0 6px 18px rgba(16,185,129,0.44)"
                    : `0 6px 18px ${ACCENT}55`,
                  "&:hover": {
                    background: keyCopied
                      ? "linear-gradient(135deg, #10b981 0%, #047857 100%)"
                      : `linear-gradient(135deg, ${ACCENT} 0%, #155e75 100%)`,
                  },
                }}
              >
                {keyCopied ? "Copied to clipboard" : t("proxy.copyTip") || "Copy key"}
              </Button>

              <Typography variant="caption" color="text.secondary" sx={{ textAlign: "center" }}>
                {t("proxy.copyReveal")}
              </Typography>
            </Stack>
          ) : (
            <Stack spacing={2.25}>
              <TextField
                label={t("proxy.fieldName")}
                size="small"
                fullWidth
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                helperText={t("proxy.fieldNameHelp")}
              />

              <Autocomplete
                multiple
                size="small"
                options={info.models}
                value={form.models}
                onChange={(_, val) => setForm({ ...form, models: val })}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t("proxy.fieldModels")}
                    helperText={t("proxy.fieldModelsHelp")}
                  />
                )}
                renderTags={(value, getTagProps) =>
                  value.map((option, index) => {
                    const props = getTagProps({ index });
                    return (
                      <Chip
                        {...props}
                        key={option}
                        label={option}
                        size="small"
                        sx={{
                          fontFamily: FONT_MONO,
                          fontSize: "0.7rem",
                          backgroundColor: ACCENT_SOFT,
                          color: ACCENT,
                          border: `1px solid ${ACCENT}33`,
                        }}
                      />
                    );
                  })
                }
              />

              <Box>
                <Typography
                  variant="overline"
                  sx={{
                    color: "text.secondary",
                    fontWeight: 600,
                    letterSpacing: 1.2,
                    fontSize: "0.65rem",
                    mb: 0.5,
                    display: "block",
                  }}
                >
                  Budget
                </Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                  <TextField
                    label={t("proxy.fieldMaxBudget")}
                    size="small"
                    type="number"
                    fullWidth
                    value={form.max_budget}
                    onChange={(e) => setForm({ ...form, max_budget: e.target.value })}
                    helperText={t("proxy.fieldMaxBudgetHelp")}
                    InputProps={{
                      endAdornment: (
                        <Box component="span" sx={{ color: "text.disabled", fontSize: "0.85rem" }}>€</Box>
                      ),
                    }}
                  />
                  <TextField
                    select
                    label={t("proxy.fieldBudgetReset")}
                    size="small"
                    fullWidth
                    value={form.duration_budget}
                    onChange={(e) => setForm({ ...form, duration_budget: e.target.value })}
                    helperText={t("proxy.fieldBudgetResetHelp")}
                  >
                    {DURATIONS.map((d) => (
                      <MenuItem key={d.value} value={d.value}>{d.label}</MenuItem>
                    ))}
                  </TextField>
                </Stack>
              </Box>

              <Box>
                <Typography
                  variant="overline"
                  sx={{
                    color: "text.secondary",
                    fontWeight: 600,
                    letterSpacing: 1.2,
                    fontSize: "0.65rem",
                    mb: 0.5,
                    display: "block",
                  }}
                >
                  Rate limits
                </Typography>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
                  <TextField
                    label={t("proxy.fieldRpm")}
                    size="small"
                    type="number"
                    fullWidth
                    value={form.rpm}
                    onChange={(e) => setForm({ ...form, rpm: e.target.value })}
                    helperText={t("proxy.fieldRpmHelp")}
                  />
                  <TextField
                    label={t("proxy.fieldTpm")}
                    size="small"
                    type="number"
                    fullWidth
                    value={form.tpm}
                    onChange={(e) => setForm({ ...form, tpm: e.target.value })}
                    helperText={t("proxy.fieldTpmHelp")}
                  />
                </Stack>
              </Box>
            </Stack>
          )}
        </DialogContent>
        <Divider />
        <DialogActions sx={{ px: 3, py: 2 }}>
          {createdKey ? (
            <Button
              onClick={closeDialog}
              variant="outlined"
              sx={{ textTransform: "none", fontWeight: 600 }}
            >
              {t("proxy.done") || "Done"}
            </Button>
          ) : (
            <>
              <Button
                onClick={closeDialog}
                sx={{ textTransform: "none", color: "text.secondary" }}
              >
                {t("common.cancel")}
              </Button>
              <Button
                onClick={handleCreate}
                variant="contained"
                disabled={creating}
                startIcon={creating ? <CircularProgress size={16} color="inherit" /> : <AddIcon />}
                sx={{
                  textTransform: "none",
                  fontWeight: 700,
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #0e7490 100%)`,
                  boxShadow: `0 4px 14px ${ACCENT}55`,
                  "&:hover": {
                    background: `linear-gradient(135deg, ${ACCENT} 0%, #155e75 100%)`,
                  },
                }}
              >
                {creating ? t("proxy.creating") : t("proxy.createKey")}
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>
    </Container>
  );
}
