import { useEffect, useState } from "react";
import { Box, Tooltip, Typography, useTheme } from "@mui/material";
import BoltIcon from "@mui/icons-material/Bolt";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import {
  buildLiveTimeline,
  estimateTokens,
  formatMs,
  traceToSegments,
} from "app/utils/runTelemetry";

// Reference dataviz palette, validated for both modes with the skill's
// validator: categorical slot 1 (blue) = LLM time, slot 3 (aqua) = tool
// execution — orange was rejected because error-red↔orange fails CVD
// separation in dark mode. Status colors are reserved for error/fallback
// and always ship with a text label or tooltip, never color alone.
const SERIES = {
  light: { llm: "#2a78d6", tool: "#1baf7a", error: "#d03b3b", warning: "#fab219" },
  dark: { llm: "#3987e5", tool: "#199e70", error: "#d03b3b", warning: "#fab219" },
};

const FONT_MONO = '"JetBrains Mono", "Fira Code", monospace';

function useSeries() {
  const theme = useTheme();
  return SERIES[theme.palette.mode === "dark" ? "dark" : "light"];
}

function StatChip({ label, value, danger }) {
  return (
    <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.5, mr: 2 }}>
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", letterSpacing: "0.12em", color: "text.disabled", fontWeight: 700 }}>
        {label}
      </Typography>
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.8rem", fontWeight: 700, color: danger ? "error.main" : "text.primary" }}>
        {value}
      </Typography>
    </Box>
  );
}

// Horizontal timeline bar for one persisted tool_trace: sequential llm/tool
// segments laid out by duration. Used per-turn in the conversation details
// dialog. Height stays small so it reads as a sparkline-grade mark.
export function TraceTimelineBar({ trace, height = 14 }) {
  const series = useSeries();
  const { spanMs, segments } = traceToSegments(trace);
  if (!segments.length) return null;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
      <Box sx={{ position: "relative", flex: 1, height, borderRadius: "4px", backgroundColor: "action.hover", overflow: "hidden" }}>
        {segments.map((s, i) => (
          s.widthPct > 0 ? (
            <Tooltip key={i} arrow title={`${s.label} · ${formatMs(s.duration)}${s.status === "error" ? " · ERROR" : ""}`}>
              <Box
                sx={{
                  position: "absolute",
                  left: `${s.startPct}%`,
                  width: `calc(${s.widthPct}% - 1px)`,
                  top: 2,
                  bottom: 2,
                  borderRadius: "3px",
                  backgroundColor:
                    s.status === "error" ? series.error
                      : s.kind === "llm" ? series.llm : series.tool,
                }}
              />
            </Tooltip>
          ) : (
            <Tooltip key={i} arrow title={s.label}>
              <Box sx={{
                position: "absolute", left: `calc(${s.startPct}% - 1px)`, width: 2,
                top: 0, bottom: 0, backgroundColor: series.warning,
              }} />
            </Tooltip>
          )
        ))}
      </Box>
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.secondary", flexShrink: 0 }}>
        {formatMs(spanMs)}
      </Typography>
    </Box>
  );
}

export function TimelineLegend() {
  const series = useSeries();
  const entry = (color, label) => (
    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
      <Box sx={{ width: 10, height: 10, borderRadius: "3px", backgroundColor: color }} />
      <Typography sx={{ fontSize: "0.65rem", color: "text.secondary" }}>{label}</Typography>
    </Box>
  );
  return (
    <Box sx={{ display: "flex", gap: 1.5, alignItems: "center" }}>
      {entry(series.llm, "LLM")}
      {entry(series.tool, "Tool")}
      {entry(series.error, "Error")}
    </Box>
  );
}

// Live playground telemetry: run clock + tool-call timeline building in real
// time from the streaming SSE frames. `toolCalls` is ChatPanel's
// streamingToolCalls; when the run finishes the strip freezes at its final
// state until the next question starts.
export default function RunTelemetry({ active, startedAt, toolCalls, outputChars, fallbacks }) {
  const series = useSeries();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [active]);

  if (!startedAt) return null;
  const endNow = active ? now : Math.max(
    startedAt,
    ...(toolCalls || []).map((c) => (c.startedAt || 0) + (c.latency_ms || 0)),
    now,
  );
  const { rows, spanMs, errors, running } = buildLiveTimeline(toolCalls, startedAt, active ? now : endNow);

  return (
    <Box
      data-testid="run-telemetry"
      sx={{
        border: "1px solid",
        borderColor: "divider",
        borderRadius: 1.5,
        px: 1.5,
        py: 1,
        mb: 1,
        backgroundColor: "background.paper",
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", flexWrap: "wrap", rowGap: 0.5 }}>
        {active ? (
          <Box
            sx={{
              width: 8, height: 8, borderRadius: "50%", mr: 0.75, flexShrink: 0,
              backgroundColor: series.tool,
              "@keyframes telemetryPulse": {
                "0%": { boxShadow: `0 0 0 0 ${series.tool}66` },
                "70%": { boxShadow: `0 0 0 6px ${series.tool}00` },
                "100%": { boxShadow: `0 0 0 0 ${series.tool}00` },
              },
              animation: "telemetryPulse 1.6s ease-out infinite",
            }}
          />
        ) : (
          <BoltIcon sx={{ fontSize: 14, mr: 0.5, color: "text.disabled" }} />
        )}
        <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", letterSpacing: "0.16em", fontWeight: 700, color: "text.disabled", mr: 2 }}>
          RUN TELEMETRY
        </Typography>
        <StatChip label="ELAPSED" value={formatMs(active ? now - startedAt : spanMs)} />
        <StatChip label="TOOLS" value={`${rows.length}${running ? ` (${running} live)` : ""}`} />
        {errors > 0 && (
          <Box sx={{ display: "flex", alignItems: "center", mr: 2 }}>
            <ErrorOutlineIcon sx={{ fontSize: 13, color: "error.main", mr: 0.25 }} />
            <StatChip label="ERRORS" value={errors} danger />
          </Box>
        )}
        {fallbacks > 0 && <StatChip label="LLM FALLBACKS" value={fallbacks} danger />}
        <StatChip label="~OUT TOKENS" value={estimateTokens(outputChars).toLocaleString()} />
      </Box>

      {active && rows.length === 0 && (
        <Box
          sx={{
            mt: 0.75, height: 4, borderRadius: 2, overflow: "hidden",
            position: "relative", backgroundColor: "action.hover",
          }}
        >
          <Box
            sx={{
              position: "absolute", top: 0, bottom: 0, width: "30%",
              borderRadius: 2, backgroundColor: series.llm, opacity: 0.5,
              "@keyframes telemetrySweep": {
                "0%": { left: "-30%" },
                "100%": { left: "100%" },
              },
              animation: "telemetrySweep 1.4s ease-in-out infinite",
            }}
          />
        </Box>
      )}

      {rows.length > 0 && (
        <Box sx={{ mt: 0.75 }}>
          {rows.map((r) => (
            <Box key={r.id} sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.4 }}>
              <Typography
                sx={{
                  fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.secondary",
                  width: 130, flexShrink: 0, overflow: "hidden",
                  textOverflow: "ellipsis", whiteSpace: "nowrap", textAlign: "right",
                }}
              >
                {r.tool}
              </Typography>
              <Box sx={{ position: "relative", flex: 1, height: 12, borderRadius: "4px", backgroundColor: "action.hover" }}>
                <Tooltip arrow title={`${r.tool} · ${formatMs(r.durationMs)}${r.status === "error" ? " · ERROR" : r.status === "running" ? " · running" : ""}`}>
                  <Box
                    sx={{
                      position: "absolute",
                      left: `${r.startPct}%`,
                      width: `${r.widthPct}%`,
                      top: 2,
                      bottom: 2,
                      borderRadius: "3px",
                      backgroundColor: r.status === "error" ? series.error : series.tool,
                      opacity: r.status === "running" ? 0.55 : 1,
                      // Live bars grow on the 500ms tick — ease the growth so
                      // the strip reads as motion, not stutter.
                      transition: "width .45s linear, left .45s linear, opacity .3s ease",
                    }}
                  />
                </Tooltip>
              </Box>
              <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.62rem", color: r.status === "error" ? "error.main" : "text.disabled", width: 56, flexShrink: 0 }}>
                {r.status === "running" ? "…" : formatMs(r.durationMs)}{r.status === "error" ? " err" : ""}
              </Typography>
            </Box>
          ))}
        </Box>
      )}
    </Box>
  );
}
