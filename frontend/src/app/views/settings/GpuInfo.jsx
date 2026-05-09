import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, Checkbox, CircularProgress, Grid, IconButton,
  Switch, Tooltip, Typography, styled,
} from "@mui/material";
import {
  Memory, Refresh, Bolt, Thermostat, Speed, Save,
  CheckCircle, RadioButtonUnchecked, DeveloperBoard,
} from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import { toast } from "react-toastify";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";
import PageHero from "app/components/page/PageHero";
import { FONT_MONO, sweep, pulse, shimmer } from "app/components/page/pageStyles";

// GPU = heat / power / silicon doing real work → orange reads as
// "compute under load". Distinct from cron-amber (which is lighter
// gold), audit-indigo, logs-violet, routines-emerald, proxy-cyan,
// classifier-violet, guards-rose, evals-teal.
const ACCENT = "#f97316";        // orange-500
const ACCENT_DARK = "#ea580c";   // orange-600
const ACCENT_SOFT = "rgba(249,115,22,0.10)";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
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

function TileHeader({ icon, title, subtitle, accent = ACCENT, action }) {
  return (
    <Box
      sx={{
        px: 2.5, pt: 2, pb: 1.75,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: "1px solid rgba(15,23,42,0.06)",
        flexWrap: "wrap",
      }}
    >
      <Box
        sx={{
          width: 36, height: 36,
          flexShrink: 0,
          borderRadius: 1.5,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${accent}1a`,
          color: accent,
          "& svg": { fontSize: 20 },
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
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
}

// Parse "12345 MiB" → number, "12345" → number, "12 GB" → number-in-MiB best-effort.
const parseMiB = (raw) => {
  if (raw == null) return null;
  if (typeof raw === "number") return raw;
  const m = String(raw).match(/([\d.]+)\s*(MiB|GiB|MB|GB)?/i);
  if (!m) return null;
  let v = parseFloat(m[1]);
  const unit = (m[2] || "MiB").toUpperCase();
  if (unit === "GIB" || unit === "GB") v *= 1024;
  return v;
};

const parsePct = (raw) => {
  if (raw == null) return null;
  if (typeof raw === "number") return raw;
  const m = String(raw).match(/([\d.]+)/);
  return m ? parseFloat(m[1]) : null;
};

const parseTemp = (raw) => {
  if (raw == null) return null;
  if (typeof raw === "number") return raw;
  const m = String(raw).match(/([\d.]+)/);
  return m ? parseFloat(m[1]) : null;
};

const formatMiB = (v) => {
  if (v == null) return "—";
  if (v >= 1024) return `${(v / 1024).toFixed(1)} GiB`;
  return `${Math.round(v)} MiB`;
};

const tempColor = (t) => {
  if (t == null) return "#94a3b8";
  if (t < 50) return "#10b981";
  if (t < 75) return "#f59e0b";
  return "#ef4444";
};

const utilColor = (u) => {
  if (u == null) return "#94a3b8";
  if (u < 30) return "#94a3b8";
  if (u < 80) return ACCENT;
  return "#dc2626";
};

// Animated bar — coloured fill + faint shimmer when value is non-zero.
function MeterBar({ value, color, label, sub }) {
  const pct = Math.max(0, Math.min(100, value ?? 0));
  return (
    <Box sx={{ width: "100%", minWidth: 140 }}>
      <Box
        sx={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          mb: 0.4,
        }}
      >
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.62rem",
            color: "text.secondary",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
            fontWeight: 600,
          }}
        >
          {label}
        </Box>
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            fontWeight: 700,
            color,
          }}
        >
          {sub}
        </Box>
      </Box>
      <Box
        sx={{
          height: 6,
          borderRadius: 3,
          backgroundColor: "rgba(15,23,42,0.06)",
          overflow: "hidden",
          position: "relative",
        }}
      >
        <Box
          sx={{
            height: "100%",
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}88, ${color})`,
            borderRadius: 3,
            transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
            position: "relative",
            "&::after": pct > 0 ? {
              content: '""',
              position: "absolute",
              inset: 0,
              background:
                "linear-gradient(90deg, transparent, rgba(255,255,255,0.35), transparent)",
              backgroundSize: "200% 100%",
              animation: `${shimmer} 2.4s linear infinite`,
            } : {},
          }}
        />
      </Box>
    </Box>
  );
}

// Small mono pill — used for chip-like badges in the header strip.
function MonoPill({ label, value, color = ACCENT }) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.5,
        px: 0.85, py: 0.4,
        borderRadius: 0.75,
        border: `1px solid ${color}33`,
        backgroundColor: `${color}10`,
      }}
    >
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.6rem",
          color: "text.secondary",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
          fontWeight: 700,
        }}
      >
        {label}
      </Box>
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.72rem",
          fontWeight: 700,
          color,
        }}
      >
        {value}
      </Box>
    </Box>
  );
}

// Per-GPU tile — square card shows index, name, three meters,
// thermals, power. Selectable as a worker target via the icon button.
function GpuCard({ gpu, isSelected, onToggle }) {
  const memTotal = parseMiB(gpu.memory_total);
  const memUsed = parseMiB(gpu.memory_used);
  const memPct = memTotal && memUsed != null ? (memUsed / memTotal) * 100 : null;
  const util = parsePct(gpu.utilization);
  const temp = parseTemp(gpu.temperature);
  const power = parsePct(gpu.power_draw);
  const powerLimit = parsePct(gpu.power_limit);
  const powerPct = power != null && powerLimit ? (power / powerLimit) * 100 : null;
  const tColor = tempColor(temp);
  const uColor = utilColor(util);

  return (
    <Box
      sx={{
        position: "relative",
        borderRadius: 2,
        border: `1px solid ${isSelected ? `${ACCENT}55` : "rgba(15,23,42,0.10)"}`,
        backgroundColor: isSelected ? ACCENT_SOFT : "#fffaf5",
        p: 2,
        transition: "all 0.2s ease",
        overflow: "hidden",
        "&:hover": {
          borderColor: `${ACCENT}77`,
          boxShadow: `0 6px 18px ${ACCENT}22`,
        },
      }}
    >
      {/* Top strip — index, name, select button */}
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1.25, mb: 1.5 }}>
        <Box
          sx={{
            width: 38, height: 38,
            flexShrink: 0,
            borderRadius: 1.25,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `linear-gradient(135deg, ${ACCENT}22, ${ACCENT}10)`,
            border: `1px solid ${ACCENT}33`,
            color: ACCENT_DARK,
            fontFamily: FONT_MONO,
            fontWeight: 800,
            fontSize: "0.95rem",
          }}
        >
          {gpu.index}
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography
            sx={{
              fontWeight: 700,
              fontSize: "0.92rem",
              lineHeight: 1.15,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {gpu.name || "Unknown GPU"}
          </Typography>
          {gpu.pci_bus_id && (
            <Box
              component="span"
              sx={{
                fontFamily: FONT_MONO,
                fontSize: "0.62rem",
                color: "text.disabled",
                letterSpacing: "0.04em",
              }}
            >
              {gpu.pci_bus_id}
            </Box>
          )}
        </Box>
        <Tooltip title={isSelected ? "In worker pool" : "Excluded from worker pool"} arrow>
          <Checkbox
            checked={isSelected}
            onChange={onToggle}
            icon={<RadioButtonUnchecked />}
            checkedIcon={<CheckCircle />}
            sx={{
              p: 0.5,
              color: "rgba(15,23,42,0.25)",
              "&.Mui-checked": { color: ACCENT },
            }}
          />
        </Tooltip>
      </Box>

      {/* Three meters */}
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25 }}>
        <MeterBar
          value={util}
          color={uColor}
          label="Util"
          sub={util != null ? `${util.toFixed(0)}%` : "—"}
        />
        <MeterBar
          value={memPct}
          color={ACCENT_DARK}
          label="VRAM"
          sub={`${formatMiB(memUsed)} / ${formatMiB(memTotal)}`}
        />
        <MeterBar
          value={powerPct}
          color="#fb923c"
          label="Power"
          sub={
            power != null
              ? `${power.toFixed(0)}W${powerLimit ? ` / ${powerLimit.toFixed(0)}W` : ""}`
              : "—"
          }
        />
      </Box>

      {/* Thermal pill */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mt: 1.5, pt: 1.25, borderTop: "1px dashed rgba(15,23,42,0.08)" }}>
        <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
          <Thermostat sx={{ fontSize: 14, color: tColor }} />
          <Box
            component="span"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.78rem",
              fontWeight: 700,
              color: tColor,
            }}
          >
            {temp != null ? `${temp.toFixed(0)}°C` : "—"}
          </Box>
        </Box>
        <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.5 }}>
          <Box
            sx={{
              width: 7, height: 7,
              borderRadius: "50%",
              background: isSelected ? ACCENT : "rgba(15,23,42,0.15)",
              boxShadow: isSelected ? `0 0 8px ${ACCENT}88` : undefined,
              ...(isSelected && util != null && util > 1 && { animation: `${pulse} 2s ease-out infinite` }),
            }}
          />
          <Box
            component="span"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.62rem",
              color: isSelected ? ACCENT_DARK : "text.disabled",
              fontWeight: 700,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
            }}
          >
            {isSelected ? "Worker" : "Idle"}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

export default function GpuInfo() {
  const auth = useAuth();
  const { refreshCapabilities } = usePlatformCapabilities();

  const [gpuEnabled, setGpuEnabled] = useState(false);
  const [gpuWorkerDevices, setGpuWorkerDevices] = useState("");
  const [saving, setSaving] = useState(false);
  const [gpuInfo, setGpuInfo] = useState([]);
  const [gpuLoading, setGpuLoading] = useState(false);

  const fetchSettings = () => {
    api.get("/settings", auth.user.token)
      .then((data) => {
        setGpuEnabled(data.gpu_enabled || false);
        setGpuWorkerDevices(data.gpu_worker_devices || "");
      })
      .catch(() => {});
  };

  const fetchGpuInfo = () => {
    setGpuLoading(true);
    api.get("/settings/gpu-info", auth.user.token)
      .then((data) => setGpuInfo(data || []))
      .catch(() => setGpuInfo([]))
      .finally(() => setGpuLoading(false));
  };

  useEffect(() => {
    document.title = "RESTai - GPU";
    fetchSettings();
    fetchGpuInfo();
  }, []);

  const handleSave = () => {
    setSaving(true);
    api.patch("/settings", { gpu_enabled: gpuEnabled, gpu_worker_devices: gpuWorkerDevices }, auth.user.token)
      .then(() => {
        toast.success("GPU settings saved");
        refreshCapabilities();
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  const selectedDevices = useMemo(
    () => (gpuWorkerDevices || "").split(",").filter(Boolean),
    [gpuWorkerDevices]
  );

  const isDeviceSelected = (idx) => selectedDevices.length === 0 || selectedDevices.includes(String(idx));

  const handleToggleDevice = (gpuIdx) => {
    const current = (gpuWorkerDevices || "").split(",").filter(Boolean);
    let next;
    if (current.length === 0) {
      next = gpuInfo.map((g) => String(g.index)).filter((i) => i !== String(gpuIdx));
    } else if (current.includes(String(gpuIdx))) {
      next = current.filter((i) => i !== String(gpuIdx));
    } else {
      next = [...current, String(gpuIdx)].sort();
    }
    const allIndices = gpuInfo.map((g) => String(g.index)).sort().join(",");
    const nextStr = next.sort().join(",");
    setGpuWorkerDevices(nextStr === allIndices ? "" : nextStr);
  };

  // Aggregate stats for the hero strip.
  const totalVram = gpuInfo.reduce((acc, g) => acc + (parseMiB(g.memory_total) || 0), 0);
  const usedVram = gpuInfo.reduce((acc, g) => acc + (parseMiB(g.memory_used) || 0), 0);
  const avgUtil = gpuInfo.length
    ? gpuInfo.reduce((acc, g) => acc + (parsePct(g.utilization) || 0), 0) / gpuInfo.length
    : 0;
  const avgTemp = gpuInfo.length
    ? gpuInfo.reduce((acc, g) => acc + (parseTemp(g.temperature) || 0), 0) / gpuInfo.length
    : 0;
  const driverVer = gpuInfo[0]?.driver_version;
  const cudaVer = gpuInfo[0]?.cuda_version;

  const activeWorkers = selectedDevices.length === 0 ? gpuInfo.length : selectedDevices.length;

  return (
    <Container>
      <PageHero
        icon={<Memory sx={{ color: "#fff" }} />}
        eyebrow="SYSTEM/GPU"
        title="GPU"
        subtitle="Detected accelerators, live utilization, and worker pool selection."
        stats={[
          { glyph: "◆", color: "#fdba74", label: gpuInfo.length ? `${gpuInfo.length} device${gpuInfo.length === 1 ? "" : "s"}` : "no GPU" },
          { glyph: "▸", color: "#fb923c", label: gpuEnabled ? "enabled" : "disabled" },
          ...(gpuInfo.length > 0 ? [{ glyph: "⚡", color: "#fcd34d", label: `${activeWorkers}/${gpuInfo.length} in pool` }] : []),
        ]}
        compact
      />

      <Box sx={{ mt: 3 }}>
        <TileCard elevation={0} accent={ACCENT}>
          <TileHeader
            icon={<DeveloperBoard />}
            title="GPU acceleration"
            subtitle="Toggle GPU mode and pick which devices the worker pool can claim. Restart required after changes."
            accent={ACCENT}
            action={
              <Tooltip title="Refresh device telemetry" arrow>
                <span>
                  <IconButton
                    size="small"
                    onClick={fetchGpuInfo}
                    disabled={gpuLoading}
                    sx={{
                      color: ACCENT_DARK,
                      "&:hover": { backgroundColor: ACCENT_SOFT },
                      ...(gpuLoading && { animation: `${pulse} 1.5s ease-out infinite` }),
                    }}
                  >
                    <Refresh fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            }
          />

          {/* Toggle row */}
          <Box
            sx={{
              px: 2.5, py: 2,
              display: "flex",
              alignItems: "center",
              gap: 2,
              flexWrap: "wrap",
              borderBottom: "1px solid rgba(15,23,42,0.06)",
            }}
          >
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1.25,
                flex: 1,
                minWidth: 240,
              }}
            >
              <Switch
                checked={gpuEnabled}
                onChange={(e) => setGpuEnabled(e.target.checked)}
                disabled={!gpuLoading && gpuInfo.length === 0}
                sx={{
                  "& .MuiSwitch-thumb": { boxShadow: gpuEnabled ? `0 0 6px ${ACCENT}` : undefined },
                  "& .MuiSwitch-switchBase.Mui-checked": { color: ACCENT },
                  "& .MuiSwitch-switchBase.Mui-checked + .MuiSwitch-track": { backgroundColor: ACCENT },
                }}
              />
              <Box>
                <Typography variant="body2" sx={{ fontWeight: 700, lineHeight: 1.1 }}>
                  {gpuEnabled ? "GPU mode active" : "CPU only"}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ fontFamily: FONT_MONO, letterSpacing: "0.04em" }}>
                  changes require restart
                </Typography>
              </Box>
            </Box>
            <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
              {driverVer && <MonoPill label="DRV" value={driverVer} color={ACCENT} />}
              {cudaVer && <MonoPill label="CUDA" value={cudaVer} color={ACCENT_DARK} />}
              {gpuInfo.length > 0 && totalVram > 0 && (
                <MonoPill label="VRAM" value={`${(usedVram / 1024).toFixed(1)} / ${(totalVram / 1024).toFixed(1)} GiB`} color="#c2410c" />
              )}
              {gpuInfo.length > 0 && (
                <MonoPill label="UTIL" value={`${avgUtil.toFixed(0)}%`} color={utilColor(avgUtil)} />
              )}
              {gpuInfo.length > 0 && avgTemp > 0 && (
                <MonoPill label="TEMP" value={`${avgTemp.toFixed(0)}°C`} color={tempColor(avgTemp)} />
              )}
            </Box>
          </Box>

          {/* Devices */}
          <Box sx={{ p: 2.5 }}>
            {gpuLoading && (
              <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 5, gap: 1.25 }}>
                <CircularProgress size={32} sx={{ color: ACCENT }} />
                <Box
                  component="span"
                  sx={{
                    fontFamily: FONT_MONO,
                    fontSize: "0.72rem",
                    color: "text.secondary",
                    letterSpacing: "0.08em",
                    textTransform: "uppercase",
                  }}
                >
                  scanning silicon…
                </Box>
              </Box>
            )}

            {!gpuLoading && gpuInfo.length === 0 && (
              <Box
                sx={{
                  py: 5,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 1.25,
                }}
              >
                <Box
                  sx={{
                    width: 56, height: 56,
                    borderRadius: "50%",
                    background: `${ACCENT}10`,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    animation: `${pulse} 3s ease-out infinite`,
                  }}
                >
                  <Bolt sx={{ fontSize: 28, color: ACCENT }} />
                </Box>
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", maxWidth: 360 }}>
                  No GPUs detected on this host.
                </Typography>
                <Typography variant="caption" color="text.disabled" sx={{ textAlign: "center", maxWidth: 360 }}>
                  RESTai will continue running in CPU mode. Install NVIDIA drivers + CUDA, then refresh.
                </Typography>
              </Box>
            )}

            {!gpuLoading && gpuInfo.length > 0 && (
              <>
                <Grid container spacing={2}>
                  {gpuInfo.map((gpu) => (
                    <Grid item xs={12} sm={6} lg={4} key={gpu.index}>
                      <GpuCard
                        gpu={gpu}
                        isSelected={isDeviceSelected(gpu.index)}
                        onToggle={() => handleToggleDevice(gpu.index)}
                      />
                    </Grid>
                  ))}
                </Grid>
                <Box
                  sx={{
                    mt: 2,
                    p: 1.25,
                    borderRadius: 1.25,
                    backgroundColor: ACCENT_SOFT,
                    border: `1px solid ${ACCENT}33`,
                    display: "flex",
                    alignItems: "center",
                    gap: 1,
                  }}
                >
                  <Speed sx={{ color: ACCENT_DARK, fontSize: 16 }} />
                  <Box
                    component="span"
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.74rem",
                      color: ACCENT_DARK,
                      fontWeight: 600,
                    }}
                  >
                    {gpuWorkerDevices
                      ? `Worker pool → GPU(s) ${gpuWorkerDevices}`
                      : "Worker pool → all available GPUs"}
                  </Box>
                </Box>
              </>
            )}
          </Box>
        </TileCard>

        {/* Save bar */}
        <Box
          sx={{
            mt: 2,
            display: "flex",
            justifyContent: "flex-end",
            gap: 1,
          }}
        >
          <Button
            variant="contained"
            startIcon={saving ? <CircularProgress size={14} color="inherit" /> : <Save />}
            onClick={handleSave}
            disabled={saving}
            sx={{
              textTransform: "none",
              fontWeight: 700,
              px: 2.5,
              background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
              boxShadow: `0 4px 14px ${ACCENT}55`,
              "&:hover": {
                background: `linear-gradient(135deg, ${ACCENT} 0%, #9a3412 100%)`,
                boxShadow: `0 6px 18px ${ACCENT}77`,
              },
            }}
          >
            {saving ? "Saving…" : "Save GPU settings"}
          </Button>
        </Box>
      </Box>
    </Container>
  );
}
