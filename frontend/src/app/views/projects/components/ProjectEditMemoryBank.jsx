import { useEffect, useMemo, useRef, useState } from "react";
import { Box, Collapse, IconButton, Tooltip } from "@mui/material";
import {
  RefreshRounded, DeleteOutlineRounded, ChevronLeftRounded,
  ChevronRightRounded, VisibilityRounded, MemoryRounded,
} from "@mui/icons-material";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import ForensicCard, { RichBackdrop } from "./forensic/ForensicCard";
import {
  PALETTE, ACCENT, ACCENT_SOFT, FONT_DISPLAY, FONT_MONO,
  breath, drift, tickerIn,
} from "./forensic/styles";

// ─── Memory-bank-specific constants ──────────────────────────────────────
// Granularities walk a blue gradient (cyan → primary → deep) so depth in
// time = depth in hue, with the theme's amber secondary as the contrast
// for "month". This stays bank-local because no other tab needs it.
const GRAN = {
  conversation: { color: "#0891b2", label: "CONVERSATION" },  // cyan-600 — freshest
  day:          { color: "#1976d2", label: "DAY"          },  // theme primary blue
  week:         { color: "#1e40af", label: "WEEK"         },  // blue-800 — deeper
  month:        { color: "#f59e0b", label: "MONTH"        },  // amber (theme.blue.secondary)
};
const GRAN_ORDER = ["conversation", "day", "week", "month"];

// ─── Helpers ─────────────────────────────────────────────────────────────
function formatRelative(iso) {
  if (!iso) return "—";
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diff < 60)    return `${diff}S AGO`;
  if (diff < 3600)  return `${Math.floor(diff / 60)}M AGO`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}H AGO`;
  return `${Math.floor(diff / 86400)}D AGO`;
}

// ─── HUD components ──────────────────────────────────────────────────────
function HUDRule({ children, sx }) {
  return (
    <Box sx={{
      fontFamily: FONT_DISPLAY, fontSize: "0.7rem", letterSpacing: "0.18em",
      fontWeight: 500, color: PALETTE.ink, textTransform: "uppercase",
      display: "flex", alignItems: "center", gap: 1, ...sx,
    }}>
      {children}
    </Box>
  );
}

function MonoText({ children, color = PALETTE.ink, sx }) {
  return (
    <Box component="span" sx={{
      fontFamily: FONT_MONO, fontSize: "0.72rem", color, letterSpacing: "0.05em",
      ...sx,
    }}>{children}</Box>
  );
}

function StatPlate({ label, value, accent }) {
  const c = accent || ACCENT;
  return (
    <Box sx={{
      px: 1.5, py: 0.75, borderRadius: 0.5,
      border: `1px solid ${c}55`,
      background: `linear-gradient(180deg, ${c}0a, rgba(255,255,255,0.65))`,
      backdropFilter: "blur(6px)",
      display: "flex", flexDirection: "column", gap: 0.25, minWidth: 92,
      boxShadow: `0 1px 0 rgba(255,255,255,0.8) inset, 0 4px 12px ${c}10`,
    }}>
      <Box sx={{
        fontFamily: FONT_DISPLAY, fontSize: "0.55rem", letterSpacing: "0.22em",
        color: PALETTE.inkDim, textTransform: "uppercase",
      }}>{label}</Box>
      <Box sx={{
        fontFamily: FONT_MONO, fontSize: "1.05rem", color: c,
        fontWeight: 600, lineHeight: 1,
      }}>{value}</Box>
    </Box>
  );
}

function TokenMeter({ used, max }) {
  const pct = max > 0 ? Math.min(100, (used / max) * 100) : 0;
  const over = used > max;
  const fill = over ? "#d97706" : ACCENT;
  return (
    <Box sx={{ position: "relative" }}>
      <Box sx={{
        display: "flex", justifyContent: "space-between", alignItems: "baseline", mb: 0.5,
      }}>
        <HUDRule sx={{ color: PALETTE.inkDim }}>
          <Box sx={{
            width: 6, height: 6, borderRadius: "50%", background: fill,
            boxShadow: `0 0 6px ${fill}88`,
          }}/>
          Token capacity
        </HUDRule>
        <MonoText color={over ? "#d97706" : PALETTE.ink}>
          {used.toLocaleString()} / {max.toLocaleString()} ▸ {pct.toFixed(0)}%
        </MonoText>
      </Box>
      <Box sx={{
        height: 6, position: "relative",
        background: "rgba(25,118,210,0.06)", border: `1px solid ${PALETTE.edge}`,
        overflow: "hidden", borderRadius: 0.5,
      }}>
        <Box sx={{
          position: "absolute", inset: 0, width: `${pct}%`,
          background: `linear-gradient(90deg, ${fill}66, ${fill})`,
          boxShadow: `0 0 8px ${fill}66`,
          transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
        }}/>
        {/* Tick marks */}
        {[25, 50, 75].map(t => (
          <Box key={t} sx={{
            position: "absolute", top: 0, bottom: 0, left: `${t}%`, width: 1,
            background: "rgba(34,42,69,0.08)",
          }}/>
        ))}
      </Box>
    </Box>
  );
}

// ─── Timeline rail (mini-map of every entry across time) ────────────────
function TimelineRail({ entries, activeIdx, onSelect }) {
  // Map timestamps to a 0..1 axis. If all entries share a time, fall back
  // to even spacing so every dot is still distinguishable.
  const positioned = useMemo(() => {
    if (!entries.length) return [];
    const times = entries.map(e => new Date(e.last_source_at || e.updated_at || e.created_at || 0).getTime());
    const min = Math.min(...times);
    const max = Math.max(...times);
    const span = Math.max(1, max - min);
    return entries.map((e, i) => ({
      entry: e,
      pos: max === min ? i / Math.max(1, entries.length - 1) : (times[i] - min) / span,
      idx: i,
    }));
  }, [entries]);

  return (
    <Box sx={{ position: "relative", height: 40, mt: 1 }}>
      {/* Rail */}
      <Box sx={{
        position: "absolute", left: 0, right: 0, top: "50%", height: 1,
        background: `linear-gradient(90deg, transparent, ${PALETTE.edge}, transparent)`,
      }}/>
      {/* Tick labels */}
      <Box sx={{
        position: "absolute", left: 0, top: 0,
        fontFamily: FONT_MONO, fontSize: "0.6rem", color: PALETTE.inkFaint,
      }}>OLDEST</Box>
      <Box sx={{
        position: "absolute", right: 0, top: 0,
        fontFamily: FONT_MONO, fontSize: "0.6rem", color: PALETTE.inkFaint,
      }}>NOW</Box>
      {/* Dots — one per entry, color by granularity */}
      {positioned.map(({ entry, pos, idx }) => {
        const c = GRAN[entry.granularity]?.color || PALETTE.ink;
        const focused = idx === activeIdx;
        return (
          <Tooltip
            key={entry.id}
            title={
              <MonoText sx={{ color: PALETTE.ink, fontSize: "0.7rem" }}>
                {entry.granularity} · {entry.period_key || (entry.chat_id ? entry.chat_id.slice(0, 8) : "—")}
              </MonoText>
            }
            arrow
          >
            <Box
              role="button"
              tabIndex={0}
              onClick={() => onSelect(idx)}
              sx={{
                position: "absolute",
                left: `calc(${pos * 100}% - ${focused ? 7 : 4}px)`,
                top: `calc(50% - ${focused ? 7 : 4}px)`,
                width: focused ? 14 : 8,
                height: focused ? 14 : 8,
                borderRadius: "50%",
                background: focused ? c : `${c}99`,
                border: focused ? `1px solid ${c}` : "none",
                boxShadow: focused
                  ? `0 0 18px ${c}, 0 0 4px ${c}`
                  : `0 0 6px ${c}55`,
                cursor: "pointer",
                transition: "all 0.3s cubic-bezier(0.4,0,0.2,1)",
                animation: focused ? `${breath} 2.5s ease-in-out infinite` : undefined,
                "&:hover": { transform: "scale(1.4)" },
              }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
}

// ─── The focused memory shard (the "orb in your hand") ──────────────────
function FocusedShard({ entry, total, idx }) {
  if (!entry) return null;
  const meta = GRAN[entry.granularity] || GRAN.conversation;
  const summaryLines = (entry.summary || "").split("\n");

  return (
    <Box
      key={entry.id}
      sx={{
        position: "relative",
        borderRadius: 0.5,
        p: 3,
        mt: 2,
        background:
          `linear-gradient(135deg, rgba(255,255,255,0.92) 0%, ${meta.color}0c 100%)`,
        border: `1px solid ${meta.color}66`,
        backdropFilter: "blur(12px)",
        animation: `${breath} 3.5s ease-in-out infinite, ${tickerIn} 0.5s ease-out`,
        overflow: "hidden",
        boxShadow: `0 12px 40px ${meta.color}18, 0 1px 0 rgba(255,255,255,0.9) inset`,
        // Corner brackets, classic HUD detail
        "&::before, &::after": {
          content: '""',
          position: "absolute",
          width: 14, height: 14,
          borderColor: meta.color,
          borderStyle: "solid",
        },
        "&::before": {
          top: 6, left: 6, borderWidth: "1px 0 0 1px",
        },
        "&::after": {
          bottom: 6, right: 6, borderWidth: "0 1px 1px 0",
        },
      }}
    >
      {/* Top header: granularity badge + period + counter */}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, mb: 1.5 }}>
        <Box sx={{
          display: "flex", alignItems: "center", gap: 0.75,
          px: 1, py: 0.4, borderRadius: 0.5,
          border: `1px solid ${meta.color}88`,
          background: `${meta.color}1c`,
        }}>
          <Box sx={{
            width: 6, height: 6, transform: "rotate(45deg)",
            background: meta.color, boxShadow: `0 0 6px ${meta.color}aa`,
          }}/>
          <Box sx={{
            fontFamily: FONT_DISPLAY, fontSize: "0.65rem",
            letterSpacing: "0.22em", color: meta.color, fontWeight: 700,
          }}>{meta.label}</Box>
        </Box>
        <MonoText color={PALETTE.ink} sx={{ fontWeight: 500, fontSize: "0.85rem" }}>
          {entry.period_key || (entry.chat_id ? entry.chat_id : "—")}
        </MonoText>
        <Box sx={{ flex: 1 }} />
        <MonoText color={PALETTE.inkDim}>
          ▸ {String(idx + 1).padStart(2, "0")} / {String(total).padStart(2, "0")}
        </MonoText>
      </Box>

      {/* Top divider */}
      <Box sx={{
        height: 1, mb: 1.5,
        background: `linear-gradient(90deg, ${meta.color}88, transparent)`,
      }}/>

      {/* Summary body */}
      <Box sx={{
        fontFamily: FONT_MONO, fontSize: "0.85rem",
        color: PALETTE.ink, lineHeight: 1.7,
        whiteSpace: "pre-wrap", wordBreak: "break-word",
        minHeight: 100,
        animation: `${tickerIn} 0.4s ease-out`,
      }}>
        {entry.summary?.trim() ? (
          summaryLines.map((line, i) => (
            <Box key={i} sx={{
              animation: `${tickerIn} 0.5s ease-out both`,
              animationDelay: `${i * 60}ms`,
            }}>
              {line || " "}
            </Box>
          ))
        ) : (
          <Box sx={{ fontStyle: "italic", color: PALETTE.inkFaint }}>
            ◌ NULL TRANSCRIPT
          </Box>
        )}
      </Box>

      {/* Bottom divider */}
      <Box sx={{
        height: 1, mt: 2,
        background: `linear-gradient(90deg, transparent, ${meta.color}88)`,
      }}/>

      {/* Footer metadata */}
      <Box sx={{ display: "flex", gap: 2, mt: 1.5, flexWrap: "wrap" }}>
        <MonoText color={PALETTE.inkDim}>
          ⌖ {formatRelative(entry.last_source_at || entry.updated_at || entry.created_at)}
        </MonoText>
        <MonoText color={PALETTE.inkDim}>
          Σ {entry.token_count} TOK
        </MonoText>
        {entry.source_message_count > 0 && (
          <MonoText color={PALETTE.inkDim}>
            ⊞ {entry.source_message_count} SRC
          </MonoText>
        )}
        {entry.chat_id && (
          <MonoText color={PALETTE.inkFaint} sx={{ ml: "auto" }}>
            CHAT/{entry.chat_id.slice(0, 12)}
          </MonoText>
        )}
      </Box>
    </Box>
  );
}

// ─── Lane (perspective-warped strip of all entries) ─────────────────────
function Lane({ entries, activeIdx, onSelect }) {
  const laneRef = useRef(null);
  const activeRef = useRef(null);

  // Auto-scroll the active thumb into view when index moves.
  useEffect(() => {
    if (activeRef.current) {
      activeRef.current.scrollIntoView({
        behavior: "smooth", inline: "center", block: "nearest",
      });
    }
  }, [activeIdx]);

  if (!entries.length) return null;

  return (
    <Box sx={{
      mt: 2, position: "relative",
      "&::before, &::after": {
        content: '""', position: "absolute", top: 0, bottom: 0,
        width: 60, pointerEvents: "none", zIndex: 2,
      },
      "&::before": { left: 0, background: `linear-gradient(90deg, ${PALETTE.void}f0, transparent)` },
      "&::after":  { right: 0, background: `linear-gradient(-90deg, ${PALETTE.void}f0, transparent)` },
    }}>
      <Box
        ref={laneRef}
        sx={{
          display: "flex", gap: 1, py: 1, px: 4,
          overflowX: "auto", overflowY: "visible",
          scrollSnapType: "x mandatory",
          // Slight perspective tilt for the whole lane
          perspective: "1200px",
          "&::-webkit-scrollbar": { height: 4 },
          "&::-webkit-scrollbar-track": { background: "rgba(25,118,210,0.04)" },
          "&::-webkit-scrollbar-thumb": { background: ACCENT_SOFT, borderRadius: 2 },
        }}
      >
        {entries.map((e, idx) => {
          const focused = idx === activeIdx;
          const meta = GRAN[e.granularity] || GRAN.conversation;
          const dist = Math.abs(idx - activeIdx);
          return (
            <Box
              key={e.id}
              ref={focused ? activeRef : undefined}
              role="button"
              tabIndex={0}
              onClick={() => onSelect(idx)}
              onKeyDown={(ev) => { if (ev.key === "Enter" || ev.key === " ") onSelect(idx); }}
              sx={{
                flexShrink: 0,
                width: focused ? 130 : 100,
                height: focused ? 110 : 84,
                cursor: "pointer",
                scrollSnapAlign: "center",
                position: "relative",
                borderRadius: 0.5,
                background: focused
                  ? `linear-gradient(135deg, ${meta.color}1f, rgba(255,255,255,0.85) 70%)`
                  : "rgba(255,255,255,0.7)",
                border: `1px solid ${focused ? meta.color : meta.color + "55"}`,
                p: 1, display: "flex", flexDirection: "column", gap: 0.5,
                transition: "all 0.4s cubic-bezier(0.4,0,0.2,1)",
                opacity: focused ? 1 : Math.max(0.35, 1 - dist * 0.18),
                transform: focused
                  ? "translateZ(0) scale(1)"
                  : `translateZ(-${dist * 40}px) translateY(${dist * 2}px)`,
                transformStyle: "preserve-3d",
                animation: focused ? `${drift} 4s ease-in-out infinite` : undefined,
                boxShadow: focused
                  ? `0 8px 24px ${meta.color}33, 0 0 0 1px ${meta.color}22, inset 0 1px 0 rgba(255,255,255,0.9)`
                  : "0 1px 3px rgba(34,42,69,0.06)",
                "&:hover": {
                  opacity: 1,
                  transform: focused
                    ? "translateZ(0) scale(1.04)"
                    : `translateZ(0) scale(1.02)`,
                  borderColor: meta.color,
                },
              }}
            >
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                <Box sx={{
                  width: 5, height: 5, transform: "rotate(45deg)",
                  background: meta.color, boxShadow: `0 0 4px ${meta.color}`,
                }}/>
                <Box sx={{
                  fontFamily: FONT_DISPLAY, fontSize: "0.5rem",
                  letterSpacing: "0.2em", color: meta.color,
                  textTransform: "uppercase", fontWeight: 600,
                }}>
                  {meta.label[0]}
                </Box>
                <Box sx={{ flex: 1 }} />
                <MonoText color={PALETTE.inkFaint} sx={{ fontSize: "0.55rem" }}>
                  {e.token_count}T
                </MonoText>
              </Box>
              <MonoText
                color={focused ? PALETTE.ink : PALETTE.inkDim}
                sx={{ fontSize: focused ? "0.7rem" : "0.62rem", fontWeight: 500 }}
              >
                {e.period_key || (e.chat_id ? e.chat_id.slice(0, 8) : "—")}
              </MonoText>
              <Box sx={{
                fontFamily: FONT_MONO, fontSize: "0.55rem",
                color: PALETTE.inkFaint, lineHeight: 1.3,
                display: "-webkit-box", WebkitLineClamp: focused ? 3 : 2,
                WebkitBoxOrient: "vertical", overflow: "hidden",
              }}>
                {(e.summary || "").replace(/^\s*[-•]\s*/gm, "").slice(0, 120)}
              </Box>
              <MonoText color={PALETTE.inkFaint} sx={{ mt: "auto", fontSize: "0.55rem" }}>
                {formatRelative(e.last_source_at || e.updated_at || e.created_at)}
              </MonoText>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

// ─── Live render preview (collapsible) ──────────────────────────────────
function LivePreview({ projectId, token, refreshKey }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = () => {
    setLoading(true);
    api.get(`/projects/${projectId}/memory-bank/preview`, token)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (open) load();
  }, [open, refreshKey]);

  return (
    <Box sx={{
      mt: 2, border: `1px solid ${PALETTE.edge}`, borderRadius: 0.5,
      background: "rgba(255,255,255,0.7)", backdropFilter: "blur(4px)",
      boxShadow: "0 1px 0 rgba(255,255,255,0.9) inset",
    }}>
      <Box
        onClick={() => setOpen(v => !v)}
        sx={{
          px: 1.5, py: 1, display: "flex", alignItems: "center", gap: 1,
          cursor: "pointer", userSelect: "none",
          "&:hover": { background: `${ACCENT}08` },
        }}
      >
        <VisibilityRounded sx={{ fontSize: 14, color: ACCENT }} />
        <HUDRule sx={{ color: PALETTE.ink }}>
          Live prompt projection
        </HUDRule>
        <Box sx={{ flex: 1 }} />
        {data && (
          <MonoText color={PALETTE.inkDim}>
            {data.tokens} / {data.max_tokens} TOK
          </MonoText>
        )}
        <Box sx={{
          width: 6, height: 6, borderRadius: "50%",
          background: open ? ACCENT : PALETTE.inkFaint,
          boxShadow: open ? `0 0 6px ${ACCENT}aa` : "none",
          transition: "all 0.3s",
        }}/>
      </Box>
      <Collapse in={open}>
        <Box sx={{
          borderTop: `1px solid ${PALETTE.edge}`,
          px: 2, py: 1.5,
          background: "rgba(244,246,251,0.6)",
        }}>
          {loading ? (
            <MonoText color={PALETTE.inkDim}>SCANNING…</MonoText>
          ) : data?.block ? (
            <Box component="pre" sx={{
              m: 0, fontFamily: FONT_MONO, fontSize: "0.75rem",
              color: PALETTE.ink, whiteSpace: "pre-wrap", wordBreak: "break-word",
              maxHeight: 320, overflow: "auto", lineHeight: 1.6,
            }}>
              {data.block}
            </Box>
          ) : (
            <MonoText color={PALETTE.inkDim}>
              ◌ NO PROJECTION — bank is empty or no System LLM is configured.
            </MonoText>
          )}
        </Box>
      </Collapse>
    </Box>
  );
}

// ─── Main component ─────────────────────────────────────────────────────
export default function ProjectEditMemoryBank({ project }) {
  const auth = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeIdx, setActiveIdx] = useState(0);
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (!project?.id) return;
    setLoading(true);
    api.get(`/projects/${project.id}/memory-bank`, auth.user.token)
      .then((d) => {
        setData(d);
        setActiveIdx((cur) => Math.min(cur, Math.max(0, (d.entries?.length || 1) - 1)));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project?.id, refreshTick]);

  const entries = data?.entries || [];

  // Keyboard navigation: ←/→ steps through the lane.
  useEffect(() => {
    const onKey = (e) => {
      if (e.target?.tagName === "INPUT" || e.target?.tagName === "TEXTAREA") return;
      if (e.key === "ArrowLeft" && activeIdx > 0) {
        setActiveIdx((i) => Math.max(0, i - 1));
      } else if (e.key === "ArrowRight" && activeIdx < entries.length - 1) {
        setActiveIdx((i) => Math.min(entries.length - 1, i + 1));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeIdx, entries.length]);

  const handleClear = () => {
    if (!window.confirm(
      "Wipe ALL memory bank entries for this project?\n\n"
      + "The cron will start re-summarizing new conversations on the next "
      + "tick — older context is gone forever."
    )) return;
    api.post(`/projects/${project.id}/memory-bank/clear`, {}, auth.user.token)
      .then((r) => {
        toast.success(`Purged ${r.deleted || 0} memories`);
        setRefreshTick((t) => t + 1);
      })
      .catch(() => {});
  };

  const refresh = () => setRefreshTick((t) => t + 1);

  // ─── Outer panel ─────────────────────────────────────────────────────
  const headerActions = (
    <>
      <Tooltip title="Refresh">
        <span>
          <IconButton
            onClick={refresh}
            disabled={loading}
            sx={{
              color: PALETTE.ink, border: `1px solid ${PALETTE.edge}`,
              borderRadius: 0.5, background: "rgba(255,255,255,0.7)",
              "&:hover": { borderColor: ACCENT, color: ACCENT, background: `${ACCENT}0c` },
            }}
            size="small"
          >
            <RefreshRounded fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title="Purge all memories (cannot be undone)">
        <span>
          <IconButton
            onClick={handleClear}
            disabled={!entries.length}
            sx={{
              color: PALETTE.inkDim, border: `1px solid ${PALETTE.edge}`,
              borderRadius: 0.5, background: "rgba(255,255,255,0.7)",
              "&:hover": { borderColor: "#dc2626", color: "#dc2626", background: "#dc262610" },
            }}
            size="small"
          >
            <DeleteOutlineRounded fontSize="small" />
          </IconButton>
        </span>
      </Tooltip>
    </>
  );

  return (
    <ForensicCard
      icon={<MemoryRounded />}
      title="Memory Bank"
      subtitle={
        <>PROJECT/{String(project.id).padStart(4, "0")} · READ-ONLY ARCHIVE</>
      }
      actions={headerActions}
      backdrop={RichBackdrop}
      sx={{ minHeight: 480 }}
    >
      <>
        {/* spacer left intentionally — header rendered by ForensicCard */}

        {/* ── Stats row ─────────────────────────────────────────────── */}
        {data?.enabled && (
          <Box sx={{
            display: "flex", gap: 1, mb: 2, flexWrap: "wrap",
            animation: `${tickerIn} 0.5s ease-out`,
          }}>
            <StatPlate label="Shards" value={String(data.entry_count || 0).padStart(3, "0")} />
            {GRAN_ORDER.map((g) => (
              <StatPlate
                key={g}
                label={GRAN[g].label}
                value={String(data.counts_by_granularity?.[g] || 0).padStart(2, "0")}
                accent={GRAN[g].color}
              />
            ))}
          </Box>
        )}

        {/* ── Token meter ───────────────────────────────────────────── */}
        {data?.enabled && (
          <Box sx={{ mb: 2 }}>
            <TokenMeter used={data.total_tokens || 0} max={data.max_tokens || 1} />
          </Box>
        )}

        {/* ── Empty / disabled states ────────────────────────────────── */}
        {!data?.enabled ? (
          <Box sx={{
            border: `1px dashed ${PALETTE.edge}`, borderRadius: 0.5, p: 3,
            display: "flex", flexDirection: "column", alignItems: "center", gap: 1,
          }}>
            <Box sx={{
              width: 36, height: 36, borderRadius: "50%",
              border: `1px solid ${PALETTE.inkFaint}`,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>◌</Box>
            <HUDRule sx={{ color: PALETTE.inkDim }}>System offline</HUDRule>
            <MonoText color={PALETTE.inkFaint} sx={{ textAlign: "center", maxWidth: 380 }}>
              Memory bank is disabled for this project. Enable it in
              GENERAL ▸ MEMORY BANK to begin aggregating conversation
              summaries shared across all members.
            </MonoText>
          </Box>
        ) : entries.length === 0 ? (
          <Box sx={{
            border: `1px dashed ${PALETTE.edge}`, borderRadius: 0.5, p: 3,
            textAlign: "center",
          }}>
            <HUDRule sx={{ color: PALETTE.inkDim, justifyContent: "center", mb: 1 }}>
              ◌ Awaiting first transmission
            </HUDRule>
            <MonoText color={PALETTE.inkFaint}>
              Cron summarizes conversations once they've been idle ≥ 10 min.
              Bank populates on the next tick after a System LLM is set.
            </MonoText>
          </Box>
        ) : (
          <>
            {/* ── Timeline rail ──────────────────────────────────────── */}
            <TimelineRail entries={entries} activeIdx={activeIdx} onSelect={setActiveIdx} />

            {/* ── Focused shard ──────────────────────────────────────── */}
            <FocusedShard entry={entries[activeIdx]} total={entries.length} idx={activeIdx} />

            {/* ── Lane navigator ─────────────────────────────────────── */}
            <Box sx={{
              display: "flex", alignItems: "center", gap: 0.5, mt: 1,
            }}>
              <IconButton
                onClick={() => setActiveIdx((i) => Math.max(0, i - 1))}
                disabled={activeIdx === 0}
                sx={{
                  color: PALETTE.ink,
                  "&:hover": { color: ACCENT },
                  "&.Mui-disabled": { color: PALETTE.inkFaint },
                }}
              >
                <ChevronLeftRounded />
              </IconButton>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Lane entries={entries} activeIdx={activeIdx} onSelect={setActiveIdx} />
              </Box>
              <IconButton
                onClick={() => setActiveIdx((i) => Math.min(entries.length - 1, i + 1))}
                disabled={activeIdx >= entries.length - 1}
                sx={{
                  color: PALETTE.ink,
                  "&:hover": { color: ACCENT },
                  "&.Mui-disabled": { color: PALETTE.inkFaint },
                }}
              >
                <ChevronRightRounded />
              </IconButton>
            </Box>

            <Box sx={{ display: "flex", justifyContent: "center", mt: 0.5 }}>
              <MonoText color={PALETTE.inkFaint} sx={{ fontSize: "0.6rem" }}>
                ◀ ARROW KEYS TO NAVIGATE ▶
              </MonoText>
            </Box>

            {/* ── Live render preview ────────────────────────────────── */}
            <LivePreview
              projectId={project.id}
              token={auth.user.token}
              refreshKey={refreshTick}
            />
          </>
        )}
      </>
    </ForensicCard>
  );
}
