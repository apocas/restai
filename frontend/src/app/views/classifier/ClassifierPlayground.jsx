import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Grid, IconButton, InputAdornment, LinearProgress,
  MenuItem, styled, TextField, Tooltip, Typography,
} from "@mui/material";
import {
  Category, Bolt, EmojiEvents, Add, Close, Replay, AutoAwesome,
} from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toast } from "react-toastify";
import { Trans, useTranslation } from "react-i18next";
import PageHero from "app/components/page/PageHero";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Page accent — violet for "classification / taxonomy". Distinct from
// chat=emerald, embeddings=indigo, images=violet-light, audio=cyan.
const ACCENT = "#7c3aed";
const ACCENT_SOFT = "rgba(124,58,237,0.10)";

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
  height: "100%",
  display: "flex",
  flexDirection: "column",
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

const TileHeader = ({ icon, title, accent = ACCENT, action }) => (
  <Box
    sx={{
      px: 3,
      pt: 2.75,
      pb: 2,
      display: "flex",
      alignItems: "center",
      gap: 1.5,
      borderBottom: "1px solid rgba(15,23,42,0.06)",
    }}
  >
    <Box
      sx={{
        width: 40,
        height: 40,
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
    <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.1, flex: 1 }}>
      {title}
    </Typography>
    {action}
  </Box>
);

// Quick-start templates so the playground isn't an empty form on first
// visit. Single click populates both the text + labels.
const QUICK_STARTS = [
  {
    name: "Sentiment",
    glyph: "♥",
    color: "#ec4899",
    sequence: "I just tried the new product and honestly I'm blown away — works exactly as advertised.",
    labels: ["positive", "neutral", "negative"],
  },
  {
    name: "Intent",
    glyph: "↻",
    color: "#0891b2",
    sequence: "I need help cancelling my subscription, the auto-renew charged me again.",
    labels: ["billing", "tech support", "feedback", "sales", "cancellation"],
  },
  {
    name: "Topic",
    glyph: "▣",
    color: "#10b981",
    sequence: "The Federal Reserve raised interest rates by 25 basis points yesterday afternoon.",
    labels: ["politics", "finance", "sports", "technology", "entertainment"],
  },
  {
    name: "Urgency",
    glyph: "!",
    color: "#f59e0b",
    sequence: "Production is down for half of EU customers, please help ASAP.",
    labels: ["critical", "high", "medium", "low"],
  },
];

export default function ClassifierPlayground() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [sequence, setSequence] = useState("");
  const [labels, setLabels] = useState([]); // chip-based
  const [labelDraft, setLabelDraft] = useState("");
  const [selectedModel, setSelectedModel] = useState("");
  const [classifiers, setClassifiers] = useState([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("classifier.title");
    api.get("/tools/classifiers", auth.user.token)
      .then((data) => {
        setClassifiers(data.classifiers || []);
        setDefaultModel(data.default || "");
        setSelectedModel(data.default || "");
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const addLabel = (raw) => {
    const v = (raw || "").trim();
    if (!v) return;
    if (labels.includes(v)) {
      setLabelDraft("");
      return;
    }
    setLabels((prev) => [...prev, v]);
    setLabelDraft("");
  };

  const handleLabelKeyDown = (e) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addLabel(labelDraft);
    } else if (e.key === "Backspace" && !labelDraft && labels.length > 0) {
      setLabels((prev) => prev.slice(0, -1));
    }
  };

  const handleClassify = () => {
    if (!sequence.trim() || labels.length === 0) {
      toast.warning(t("classifier.enterBoth"));
      return;
    }
    setLoading(true);
    setResults(null);
    const body = { sequence: sequence.trim(), labels };
    if (selectedModel && selectedModel !== defaultModel) body.model = selectedModel;
    api.post("/tools/classifier", body, auth.user.token)
      .then((data) => setResults(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const applyQuickStart = (q) => {
    setSequence(q.sequence);
    setLabels(q.labels);
    setLabelDraft("");
    setResults(null);
  };

  const handleReset = () => {
    setSequence("");
    setLabels([]);
    setLabelDraft("");
    setResults(null);
  };

  const canClassify = sequence.trim() && labels.length > 0 && !loading;
  const activeClassifier = classifiers.find((c) => c.id === selectedModel);

  return (
    <Container>
      <PageHero
        icon={<Category sx={{ color: "#fff" }} />}
        eyebrow="ZERO-SHOT CLASSIFICATION"
        title={t("classifier.title") || "Classifier"}
        subtitle="Score arbitrary text against any set of labels. No training, no fine-tune — paste a sentence, pick the buckets, get probabilities."
        stats={[
          { glyph: "◆", color: "#c4b5fd", label: `${classifiers.length} classifier${classifiers.length === 1 ? "" : "s"}` },
          ...(defaultModel ? [{ glyph: "★", color: "#7dd3fc", label: `default · ${defaultModel}` }] : []),
        ]}
      />

      {/* Quick-start strip */}
      <Box sx={{ mb: 3 }}>
        <Typography
          variant="overline"
          sx={{
            display: "block",
            color: "text.secondary",
            fontWeight: 600,
            letterSpacing: 1.2,
            mb: 1,
            fontSize: "0.65rem",
          }}
        >
          Quick starts
        </Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
          {QUICK_STARTS.map((q) => (
            <Tooltip key={q.name} title={q.sequence} placement="top" arrow>
              <Chip
                onClick={() => applyQuickStart(q)}
                label={
                  <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                    <Box component="span" sx={{ color: q.color, fontWeight: 700, fontSize: "0.95rem" }}>
                      {q.glyph}
                    </Box>
                    <span>{q.name}</span>
                  </Box>
                }
                variant="outlined"
                sx={{
                  cursor: "pointer",
                  height: 30,
                  fontWeight: 500,
                  borderColor: `${q.color}55`,
                  color: "text.primary",
                  background: "#fff",
                  transition: "all 0.18s ease",
                  "&:hover": {
                    borderColor: q.color,
                    backgroundColor: `${q.color}10`,
                    transform: "translateY(-1px)",
                    boxShadow: `0 4px 12px ${q.color}22`,
                  },
                }}
              />
            </Tooltip>
          ))}
          {(sequence || labels.length > 0) && (
            <Tooltip title="Clear all" placement="top" arrow>
              <Chip
                onClick={handleReset}
                icon={<Replay fontSize="small" />}
                label="Reset"
                variant="outlined"
                sx={{
                  cursor: "pointer",
                  height: 30,
                  borderColor: "rgba(15,23,42,0.16)",
                  color: "text.secondary",
                  ml: 0.5,
                  "&:hover": {
                    borderColor: "rgba(15,23,42,0.4)",
                    backgroundColor: "rgba(15,23,42,0.04)",
                  },
                }}
              />
            </Tooltip>
          )}
        </Box>
      </Box>

      <Grid container spacing={3}>
        {/* ── Input ───────────────────────────────────── */}
        <Grid item xs={12} md={6}>
          <TileCard elevation={0} accent={ACCENT}>
            <TileHeader icon={<AutoAwesome />} title={t("classifier.playgroundTitle") || "Playground"} accent={ACCENT} />

            <Box sx={{ p: 3, pt: 2.5, display: "flex", flexDirection: "column", gap: 2.25, flex: 1 }}>
              {/* Model picker */}
              <TextField
                fullWidth
                select
                label={t("classifier.model")}
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                helperText={t("classifier.modelHelp")}
                size="small"
              >
                {classifiers.map((c) => (
                  <MenuItem key={c.id} value={c.id}>
                    <Box sx={{ display: "inline-flex", alignItems: "center", gap: 1 }}>
                      <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>
                        {c.name}
                      </Box>
                      {c.id === defaultModel && (
                        <Chip
                          label="default"
                          size="small"
                          sx={{
                            height: 16,
                            fontSize: "0.6rem",
                            fontWeight: 600,
                            backgroundColor: ACCENT_SOFT,
                            color: ACCENT,
                            "& .MuiChip-label": { px: 0.75 },
                          }}
                        />
                      )}
                    </Box>
                  </MenuItem>
                ))}
              </TextField>

              {/* Text area */}
              <TextField
                fullWidth
                multiline
                rows={5}
                label={t("classifier.textLabel")}
                placeholder={t("classifier.textPlaceholder")}
                value={sequence}
                onChange={(e) => setSequence(e.target.value)}
                InputProps={{
                  sx: {
                    fontFamily: FONT_MONO,
                    fontSize: "0.85rem",
                    lineHeight: 1.55,
                  },
                }}
                helperText={
                  sequence
                    ? `${sequence.length} chars · ${sequence.trim().split(/\s+/).filter(Boolean).length} words`
                    : " "
                }
              />

              {/* Labels — chip input */}
              <Box>
                <TextField
                  fullWidth
                  size="small"
                  label={t("classifier.labels")}
                  placeholder={labels.length === 0 ? t("classifier.labelsPlaceholder") || "type a label and press Enter…" : "+ add another label"}
                  value={labelDraft}
                  onChange={(e) => setLabelDraft(e.target.value)}
                  onKeyDown={handleLabelKeyDown}
                  onBlur={() => addLabel(labelDraft)}
                  helperText={t("classifier.labelsHelp") || "Press Enter or comma to add. Backspace on an empty input removes the last."}
                  InputProps={{
                    endAdornment: labelDraft.trim() && (
                      <InputAdornment position="end">
                        <IconButton
                          size="small"
                          onClick={() => addLabel(labelDraft)}
                          sx={{ color: ACCENT }}
                        >
                          <Add fontSize="small" />
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />
                {labels.length > 0 && (
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, mt: 1.25 }}>
                    {labels.map((l) => (
                      <Chip
                        key={l}
                        label={l}
                        size="small"
                        onDelete={() => setLabels((prev) => prev.filter((x) => x !== l))}
                        deleteIcon={<Close fontSize="small" />}
                        sx={{
                          height: 26,
                          backgroundColor: ACCENT_SOFT,
                          color: ACCENT,
                          fontWeight: 600,
                          border: `1px solid ${ACCENT}33`,
                          "& .MuiChip-deleteIcon": {
                            color: `${ACCENT}cc`,
                            "&:hover": { color: ACCENT },
                          },
                        }}
                      />
                    ))}
                  </Box>
                )}
              </Box>

              <Box sx={{ flex: 1 }} />

              <Button
                variant="contained"
                onClick={handleClassify}
                disabled={!canClassify}
                fullWidth
                size="large"
                startIcon={<Bolt />}
                sx={{
                  textTransform: "none",
                  fontWeight: 700,
                  letterSpacing: 0.2,
                  py: 1.25,
                  background: `linear-gradient(135deg, ${ACCENT} 0%, #6366f1 100%)`,
                  boxShadow: `0 6px 18px ${ACCENT}44`,
                  "&:hover": {
                    background: `linear-gradient(135deg, ${ACCENT} 0%, #4f46e5 100%)`,
                    boxShadow: `0 8px 24px ${ACCENT}66`,
                  },
                  "&.Mui-disabled": {
                    background: "rgba(15,23,42,0.08)",
                    color: "rgba(15,23,42,0.35)",
                  },
                }}
              >
                {loading ? t("classifier.classifying") : t("classifier.classify")}
              </Button>
            </Box>
          </TileCard>
        </Grid>

        {/* ── Results ─────────────────────────────────── */}
        <Grid item xs={12} md={6}>
          <TileCard elevation={0} accent={results ? "#10b981" : ACCENT}>
            <TileHeader
              icon={<EmojiEvents />}
              title={t("classifier.results") || "Results"}
              accent={results ? "#10b981" : ACCENT}
              action={
                activeClassifier && results && (
                  <Box
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.65rem",
                      color: "text.disabled",
                      letterSpacing: "0.05em",
                    }}
                  >
                    {activeClassifier.name}
                  </Box>
                )
              }
            />

            <Box sx={{ p: 3, pt: 2.5, flex: 1, display: "flex", flexDirection: "column" }}>
              {loading && (
                <Box sx={{ mb: 2 }}>
                  <LinearProgress
                    sx={{
                      height: 4,
                      borderRadius: 2,
                      backgroundColor: ACCENT_SOFT,
                      "& .MuiLinearProgress-bar": { backgroundColor: ACCENT },
                    }}
                  />
                  <Typography
                    variant="caption"
                    sx={{
                      display: "block",
                      mt: 1,
                      fontFamily: FONT_MONO,
                      fontSize: "0.7rem",
                      color: ACCENT,
                      letterSpacing: "0.1em",
                    }}
                  >
                    SCORING…
                  </Typography>
                </Box>
              )}

              {!results && !loading && (
                <Box
                  sx={{
                    flex: 1,
                    minHeight: 280,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "text.secondary",
                    textAlign: "center",
                    gap: 1.25,
                  }}
                >
                  <Box
                    sx={{
                      width: 64,
                      height: 64,
                      borderRadius: "50%",
                      background: ACCENT_SOFT,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      animation: `${pulse} 3s ease-out infinite`,
                    }}
                  >
                    <Category sx={{ fontSize: 32, color: ACCENT }} />
                  </Box>
                  <Typography variant="body2" sx={{ maxWidth: 260, color: "text.secondary" }}>
                    {t("classifier.inputHint")}
                  </Typography>
                </Box>
              )}

              {results && (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  {/* Echo of the input */}
                  <Box
                    sx={{
                      p: 1.75,
                      borderRadius: 1.5,
                      backgroundColor: "rgba(15,23,42,0.025)",
                      border: "1px solid rgba(15,23,42,0.06)",
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{
                        display: "block",
                        fontFamily: FONT_MONO,
                        fontSize: "0.6rem",
                        letterSpacing: "0.18em",
                        fontWeight: 700,
                        color: "text.disabled",
                        mb: 0.5,
                      }}
                    >
                      INPUT
                    </Typography>
                    <Typography
                      variant="body2"
                      sx={{
                        fontFamily: FONT_MONO,
                        fontSize: "0.78rem",
                        color: "text.secondary",
                        lineHeight: 1.55,
                      }}
                    >
                      "{results.sequence}"
                    </Typography>
                  </Box>

                  {/* Score bars */}
                  <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                    {results.labels.map((label, i) => {
                      const score = results.scores[i];
                      const pct = (score * 100).toFixed(1);
                      const isWinner = i === 0;
                      const barColor = isWinner ? "#10b981" : "#94a3b8";
                      return (
                        <Box key={label}>
                          <Box
                            sx={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              mb: 0.5,
                            }}
                          >
                            <Box sx={{ display: "inline-flex", alignItems: "center", gap: 0.75 }}>
                              {isWinner && (
                                <EmojiEvents sx={{ fontSize: 16, color: "#10b981" }} />
                              )}
                              <Typography
                                sx={{
                                  fontWeight: isWinner ? 700 : 500,
                                  fontSize: "0.85rem",
                                  color: isWinner ? "#10b981" : "text.primary",
                                }}
                              >
                                {label}
                              </Typography>
                            </Box>
                            <Typography
                              sx={{
                                fontFamily: FONT_MONO,
                                fontWeight: isWinner ? 700 : 500,
                                fontSize: "0.85rem",
                                color: isWinner ? "#10b981" : "text.secondary",
                              }}
                            >
                              {pct}%
                            </Typography>
                          </Box>
                          <Box
                            sx={{
                              position: "relative",
                              height: 8,
                              borderRadius: 4,
                              backgroundColor: "rgba(15,23,42,0.06)",
                              overflow: "hidden",
                            }}
                          >
                            <Box
                              sx={{
                                position: "absolute",
                                left: 0, top: 0, bottom: 0,
                                width: `${score * 100}%`,
                                background: isWinner
                                  ? "linear-gradient(90deg, #10b981 0%, #34d399 100%)"
                                  : barColor,
                                borderRadius: 4,
                                transition: "width 0.6s cubic-bezier(0.4,0,0.2,1)",
                                boxShadow: isWinner ? "0 0 12px rgba(16,185,129,0.4)" : "none",
                              }}
                            />
                          </Box>
                        </Box>
                      );
                    })}
                  </Box>

                  {/* Best-match callout */}
                  {results.labels.length > 0 && (
                    <Box
                      sx={{
                        mt: 0.5,
                        p: 1.75,
                        borderRadius: 1.5,
                        background:
                          "linear-gradient(135deg, rgba(16,185,129,0.10) 0%, rgba(34,211,238,0.06) 100%)",
                        border: "1px solid rgba(16,185,129,0.25)",
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                      }}
                    >
                      <EmojiEvents sx={{ color: "#10b981", fontSize: 20 }} />
                      <Typography variant="body2" sx={{ color: "text.secondary" }}>
                        <Trans
                          i18nKey="classifier.bestMatch"
                          values={{ label: results.labels[0], pct: (results.scores[0] * 100).toFixed(1) }}
                          components={{ strong: <strong style={{ color: "#10b981" }} /> }}
                        />
                      </Typography>
                    </Box>
                  )}
                </Box>
              )}
            </Box>
          </TileCard>
        </Grid>
      </Grid>
    </Container>
  );
}
