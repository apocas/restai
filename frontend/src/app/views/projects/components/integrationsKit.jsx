import { useState } from "react";
import { Box, IconButton, Tooltip, Typography } from "@mui/material";
import { ContentCopy, Visibility, VisibilityOff } from "@mui/icons-material";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

export const KIT_ACCENT = "#0ea5e9";

export const dotSx = (color) => ({
  width: 8,
  height: 8,
  borderRadius: "50%",
  backgroundColor: color,
  boxShadow: `0 0 8px ${color}aa`,
  flexShrink: 0,
});

export const sectionShellSx = (accent = KIT_ACCENT) => ({
  position: "relative",
  borderRadius: 2,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#fff",
  overflow: "hidden",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
    transform: "translateX(-100%)",
    animation: `${sweep} 6s linear infinite`,
    pointerEvents: "none",
    opacity: 0.55,
  },
});

export const sectionLabelSx = {
  fontFamily: FONT_MONO,
  fontSize: "0.62rem",
  letterSpacing: "0.22em",
  fontWeight: 700,
  color: "text.disabled",
  textTransform: "uppercase",
};

export function StatusDot({ state }) {
  const palette = {
    ok:    "#10b981",
    warn:  "#f59e0b",
    bad:   "#ef4444",
    empty: "rgba(15,23,42,0.18)",
  };
  return (
    <Box
      sx={{
        ...dotSx(palette[state] || palette.empty),
        animation: state === "ok" ? `${pulse} 2.6s ease-out infinite` : "none",
      }}
    />
  );
}

// Header strip used at the top of every section: title in MONO +
// optional LIVE/OFF pill (only when `live` is explicitly true/false —
// undefined skips the pill, for sections that aren't a single
// enable/disable) + optional right-aligned subtitle.
export function SectionHeader({ title, live, accent = "#10b981", subtitle, right }) {
  const showPill = typeof live === "boolean";
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap", mb: 1 }}>
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", letterSpacing: "0.18em", fontWeight: 700, textTransform: "uppercase" }}>
        {title}
      </Typography>
      {showPill && (
        <Box sx={{
          display: "inline-flex", alignItems: "center", gap: 0.6, px: 1, py: 0.35, borderRadius: 1,
          backgroundColor: live ? `${accent}1a` : "rgba(15,23,42,0.05)",
          border: `1px solid ${live ? `${accent}55` : "rgba(15,23,42,0.10)"}`,
        }}>
          <Box sx={{ ...dotSx(live ? accent : "rgba(15,23,42,0.25)"), animation: live ? `${pulse} 2.6s ease-out infinite` : "none" }} />
          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", fontWeight: 700, color: live ? accent : "text.disabled", letterSpacing: "0.06em" }}>
            {live ? "LIVE" : "OFF"}
          </Typography>
        </Box>
      )}
      <Box sx={{ flex: 1 }} />
      {subtitle && (
        <Typography sx={{ fontSize: "0.78rem", color: "text.secondary", textAlign: "right" }}>
          {subtitle}
        </Typography>
      )}
      {right}
    </Box>
  );
}

const inputBaseSx = {
  flex: 1, minWidth: 0,
  fontFamily: FONT_MONO, fontSize: "0.85rem",
  px: 1.25, py: 1,
  borderRadius: 1.25,
  border: "1px solid rgba(15,23,42,0.14)",
  backgroundColor: "#fafbfc",
  color: "text.primary",
  outline: "none",
  transition: "border-color .15s ease, box-shadow .15s ease",
  "&:focus": { borderColor: KIT_ACCENT, boxShadow: `0 0 0 3px ${KIT_ACCENT}22` },
  "&[readonly]": { color: "text.secondary", backgroundColor: "#f3f5f8" },
};

// Mono-font field with the same focus-ring accent as the webhooks
// panel. Use for any non-secret value where the rendered shape matters
// (URLs, IDs, phone numbers, etc.). `right` slot lets callers append a
// status pill or copy button.
export function MonoField({ label, value, onChange, placeholder, type = "text", readOnly, right, helper, multiline, rows = 2 }) {
  return (
    <Box>
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.secondary", mb: 0.5, letterSpacing: "0.08em", textTransform: "uppercase" }}>
        {label}
      </Typography>
      <Box sx={{ display: "flex", gap: 1, alignItems: "stretch" }}>
        <Box
          component={multiline ? "textarea" : "input"}
          type={multiline ? undefined : type}
          rows={multiline ? rows : undefined}
          value={value ?? ""}
          onChange={onChange}
          readOnly={readOnly}
          placeholder={placeholder}
          spellCheck={false}
          sx={{ ...inputBaseSx, ...(multiline ? { resize: "vertical", lineHeight: 1.5, fontFamily: FONT_MONO } : {}) }}
        />
        {right}
      </Box>
      {helper && (
        <Typography sx={{ fontSize: "0.7rem", color: "text.disabled", mt: 0.5 }}>{helper}</Typography>
      )}
    </Box>
  );
}

export function SecretField({ label, value, onChange, helper, badge, right }) {
  const [show, setShow] = useState(false);
  return (
    <Box>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
        <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.65rem", color: "text.secondary", letterSpacing: "0.08em", flex: 1, textTransform: "uppercase" }}>
          {label}
        </Typography>
        {badge}
      </Box>
      <Box sx={{ display: "flex", gap: 1, alignItems: "stretch" }}>
        <Box
          component="input"
          type={show ? "text" : "password"}
          value={value ?? ""}
          onChange={onChange}
          spellCheck={false}
          sx={inputBaseSx}
        />
        <IconButton size="small" onClick={() => setShow((v) => !v)} sx={{ border: "1px solid rgba(15,23,42,0.10)", borderRadius: 1.25 }}>
          {show ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
        </IconButton>
        {right}
      </Box>
      {helper && (
        <Typography sx={{ fontSize: "0.7rem", color: "text.disabled", mt: 0.5 }}>{helper}</Typography>
      )}
    </Box>
  );
}

export function CopyButton({ value, size = "small" }) {
  const [copied, setCopied] = useState(false);
  return (
    <Tooltip title={copied ? "copied" : "copy"} arrow>
      <IconButton
        size={size}
        onClick={() => { navigator.clipboard.writeText(value || ""); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
        sx={{ border: "1px solid rgba(15,23,42,0.10)", borderRadius: 1.25, color: "text.disabled", "&:hover": { color: KIT_ACCENT } }}
      >
        <ContentCopy sx={{ fontSize: 14 }} />
      </IconButton>
    </Tooltip>
  );
}
