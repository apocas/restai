import { useState } from "react";
import {
  Alert, Box, Card, CircularProgress, IconButton, InputAdornment,
  TextField, Tooltip, Typography,
} from "@mui/material";
import {
  TravelExploreRounded, SearchRounded, RefreshRounded,
  ContentCopyRounded,
} from "@mui/icons-material";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

// Lift the same display tokens used by ProjectEditMemoryBank so the
// two memory screens feel like a single piece. Light surface, RESTai
// blue accent, monospace data, Chakra Petch headers (loaded once via
// the bank tab's useEffect; we don't re-inject).
const PALETTE = {
  void:     "#f4f7fb",
  edge:     "rgba(25, 118, 210, 0.18)",
  ink:      "#222a45",
  inkDim:   "rgba(34, 42, 69, 0.62)",
  inkFaint: "rgba(34, 42, 69, 0.36)",
};
const ACCENT = "#1976d2";
const FONT_DISPLAY = "'Chakra Petch', ui-sans-serif, system-ui, sans-serif";
const FONT_MONO    = "'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace";

const PRESET_K = [3, 5, 10, 20];

export default function ProjectEditMemorySearch({ project }) {
  const auth = useAuth();
  const [query, setQuery] = useState("");
  const [k, setK] = useState(5);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [lastQueryRan, setLastQueryRan] = useState("");

  const runSearch = (queryText) => {
    const q = (queryText ?? query).trim();
    if (!q) return;
    setLoading(true);
    setLastQueryRan(q);
    api.post(
      `/projects/${project.id}/memory-search`,
      { query: q, k },
      auth.user.token,
    )
      .then((d) => setResult(d?.result || ""))
      .catch((e) => {
        const msg = e?.detail || e?.message || "Search failed";
        setResult(`ERROR: ${msg}`);
      })
      .finally(() => setLoading(false));
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      runSearch();
    }
  };

  const copyResult = () => {
    if (!result) return;
    navigator.clipboard.writeText(result);
    toast.success("Copied");
  };

  return (
    <Card
      elevation={0}
      sx={{
        position: "relative",
        background: PALETTE.void,
        border: `1px solid ${PALETTE.edge}`,
        borderRadius: 1,
        overflow: "hidden",
        color: PALETTE.ink,
        p: { xs: 2, md: 3 },
        minHeight: 480,
        boxShadow: "0 1px 0 rgba(255,255,255,0.9) inset, 0 8px 32px rgba(34,42,69,0.06)",
      }}
    >
      {/* Soft blue bloom — same vocabulary as the bank viewer */}
      <Box sx={{
        position: "absolute", inset: 0, pointerEvents: "none",
        background: "radial-gradient(ellipse 70% 45% at 50% -10%, rgba(25,118,210,0.10), transparent 60%)",
      }}/>
      <Box sx={{
        position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.6,
        backgroundImage:
          "linear-gradient(rgba(25,118,210,0.05) 1px, transparent 1px),"
        + "linear-gradient(90deg, rgba(25,118,210,0.05) 1px, transparent 1px)",
        backgroundSize: "24px 24px",
        maskImage: "radial-gradient(ellipse 80% 100% at 50% 0%, black 30%, transparent 90%)",
      }}/>

      <Box sx={{ position: "relative", zIndex: 1 }}>
        {/* Header */}
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
          <TravelExploreRounded sx={{
            fontSize: 18, color: ACCENT,
            filter: `drop-shadow(0 0 6px ${ACCENT}55)`,
          }}/>
          <Box>
            <Box sx={{
              fontFamily: FONT_DISPLAY, fontSize: "0.95rem",
              letterSpacing: "0.18em", fontWeight: 600,
              color: PALETTE.ink, textTransform: "uppercase",
              lineHeight: 1,
            }}>
              Memory
            </Box>
            <Box sx={{
              fontFamily: FONT_MONO, fontSize: "0.6rem",
              color: PALETTE.inkFaint, letterSpacing: "0.06em", mt: 0.25,
            }}>
              PROJECT/{String(project.id).padStart(4, "0")} ·
              SAME OUTPUT THE LLM SEES VIA <code>search_memories</code>
            </Box>
          </Box>
        </Box>

        <Typography
          variant="caption"
          sx={{ color: PALETTE.inkDim, display: "block", mt: 1, mb: 2 }}
        >
          Run an arbitrary semantic query against the project's
          conversation-history index. Result is byte-for-byte what the
          agent gets when it calls the <code>search_memories</code>{" "}
          builtin tool — useful for sanity-checking what context the
          model would surface for a given prompt.
        </Typography>

        {/* Query input */}
        <TextField
          fullWidth
          autoFocus
          placeholder='e.g. "auth flow rollout decisions"'
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={onKeyDown}
          variant="outlined"
          sx={{
            background: "rgba(255,255,255,0.85)",
            "& .MuiOutlinedInput-root": {
              fontFamily: FONT_MONO, fontSize: "0.9rem",
              "& fieldset": { borderColor: PALETTE.edge },
              "&:hover fieldset": { borderColor: ACCENT },
              "&.Mui-focused fieldset": { borderColor: ACCENT, borderWidth: 1 },
            },
          }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchRounded sx={{ color: PALETTE.inkDim, fontSize: 20 }} />
              </InputAdornment>
            ),
            endAdornment: (
              <InputAdornment position="end">
                {loading
                  ? <CircularProgress size={18} sx={{ color: ACCENT, mr: 0.5 }} />
                  : (
                    <Tooltip title="Run search (or press Enter)">
                      <span>
                        <IconButton
                          onClick={() => runSearch()}
                          disabled={!query.trim()}
                          size="small"
                          sx={{ color: ACCENT }}
                        >
                          <RefreshRounded fontSize="small" />
                        </IconButton>
                      </span>
                    </Tooltip>
                  )
                }
              </InputAdornment>
            ),
          }}
        />

        {/* k presets */}
        <Box sx={{
          display: "flex", alignItems: "center", gap: 1, mt: 1.5, mb: 2,
          flexWrap: "wrap",
        }}>
          <Box sx={{
            fontFamily: FONT_DISPLAY, fontSize: "0.6rem",
            letterSpacing: "0.22em", color: PALETTE.inkDim,
            textTransform: "uppercase",
          }}>Top‑K</Box>
          {PRESET_K.map((n) => {
            const active = n === k;
            return (
              <Box
                key={n}
                role="button"
                tabIndex={0}
                onClick={() => setK(n)}
                sx={{
                  px: 1, py: 0.25, cursor: "pointer", borderRadius: 0.5,
                  fontFamily: FONT_MONO, fontSize: "0.72rem", fontWeight: 600,
                  border: `1px solid ${active ? ACCENT : PALETTE.edge}`,
                  background: active ? `${ACCENT}1c` : "rgba(255,255,255,0.7)",
                  color: active ? ACCENT : PALETTE.inkDim,
                  transition: "all 0.2s ease",
                  "&:hover": { borderColor: ACCENT, color: ACCENT },
                }}
              >
                {n}
              </Box>
            );
          })}
          <Box sx={{ flex: 1 }} />
          {result && !loading && (
            <Tooltip title="Copy raw output">
              <IconButton size="small" onClick={copyResult} sx={{
                color: PALETTE.inkDim,
                border: `1px solid ${PALETTE.edge}`,
                borderRadius: 0.5,
                background: "rgba(255,255,255,0.7)",
                "&:hover": { borderColor: ACCENT, color: ACCENT, background: `${ACCENT}0c` },
              }}>
                <ContentCopyRounded fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </Box>

        {/* Result panel — verbatim tool output */}
        {result === null && !loading && (
          <Box sx={{
            border: `1px dashed ${PALETTE.edge}`, borderRadius: 0.5, p: 3,
            textAlign: "center",
          }}>
            <Box sx={{
              fontFamily: FONT_DISPLAY, fontSize: "0.7rem",
              letterSpacing: "0.22em", color: PALETTE.inkDim,
              textTransform: "uppercase", mb: 1,
            }}>
              ◌ Awaiting query
            </Box>
            <Box sx={{
              fontFamily: FONT_MONO, fontSize: "0.72rem",
              color: PALETTE.inkFaint,
            }}>
              Type a phrase above and press Enter. Results are sorted
              by cosine similarity.
            </Box>
          </Box>
        )}
        {loading && (
          <Box sx={{
            border: `1px solid ${PALETTE.edge}`, borderRadius: 0.5,
            background: "rgba(255,255,255,0.7)", p: 3,
            display: "flex", justifyContent: "center", alignItems: "center", gap: 1,
          }}>
            <CircularProgress size={18} sx={{ color: ACCENT }} />
            <Box sx={{
              fontFamily: FONT_MONO, fontSize: "0.75rem",
              color: PALETTE.inkDim, letterSpacing: "0.05em",
            }}>SCANNING…</Box>
          </Box>
        )}
        {result !== null && !loading && (
          <Box sx={{
            border: `1px solid ${result.startsWith("ERROR:") ? "#dc262644" : PALETTE.edge}`,
            borderRadius: 0.5,
            background: result.startsWith("ERROR:")
              ? "rgba(220, 38, 38, 0.04)"
              : "rgba(255,255,255,0.85)",
            backdropFilter: "blur(4px)",
            overflow: "hidden",
          }}>
            <Box sx={{
              px: 1.5, py: 0.75,
              borderBottom: `1px solid ${PALETTE.edge}`,
              background: "rgba(244,247,251,0.6)",
              display: "flex", alignItems: "center", gap: 1,
            }}>
              <Box sx={{
                width: 6, height: 6, borderRadius: "50%",
                background: result.startsWith("ERROR:") ? "#dc2626" : ACCENT,
                boxShadow: `0 0 6px ${result.startsWith("ERROR:") ? "#dc2626" : ACCENT}aa`,
              }}/>
              <Box sx={{
                fontFamily: FONT_DISPLAY, fontSize: "0.6rem",
                letterSpacing: "0.22em", color: PALETTE.inkDim,
                textTransform: "uppercase",
              }}>Tool output</Box>
              <Box sx={{ flex: 1 }} />
              <Box sx={{
                fontFamily: FONT_MONO, fontSize: "0.65rem",
                color: PALETTE.inkFaint,
              }}>{lastQueryRan && `query: "${lastQueryRan}"  · k=${k}`}</Box>
            </Box>
            <Box component="pre" sx={{
              m: 0, p: 2,
              fontFamily: FONT_MONO, fontSize: "0.82rem", lineHeight: 1.7,
              color: result.startsWith("ERROR:") ? "#991b1b" : PALETTE.ink,
              whiteSpace: "pre-wrap", wordBreak: "break-word",
              maxHeight: 520, overflow: "auto",
            }}>
              {result}
            </Box>
          </Box>
        )}

        {/* Privacy footnote */}
        <Alert
          severity="info"
          variant="outlined"
          sx={{ mt: 2, borderColor: PALETTE.edge, color: PALETTE.inkDim }}
        >
          Memory Search returns conversations from <strong>all users</strong>
          {" "}with access to this project, regardless of who sent them. The
          agent has the same view when it invokes the tool.
        </Alert>
      </Box>
    </Card>
  );
}
