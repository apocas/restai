import { useState } from "react";
import {
  Box, Button, Card, Chip, Grid, LinearProgress, styled,
  TextField, Typography,
} from "@mui/material";
import { Category } from "@mui/icons-material";
import Breadcrumb from "app/components/Breadcrumb";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toast } from "react-toastify";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const COLORS = ["#42a5f5", "#66bb6a", "#ffa726", "#ef5350", "#ab47bc", "#26c6da", "#5c6bc0", "#ec407a"];

export default function ClassifierPlayground() {
  const auth = useAuth();
  const [sequence, setSequence] = useState("");
  const [labelsText, setLabelsText] = useState("");
  const [results, setResults] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleClassify = () => {
    const labels = labelsText.split(",").map((l) => l.trim()).filter(Boolean);
    if (!sequence.trim() || labels.length === 0) {
      toast.warning("Enter text and at least one label");
      return;
    }

    setLoading(true);
    setResults(null);
    api.post("/tools/classifier", { sequence: sequence.trim(), labels }, auth.user.token)
      .then((data) => setResults(data))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Classifier", path: "/classifier" }]} />
      </Box>

      <ContentBox>
        <Grid container spacing={3}>
          {/* Input */}
          <Grid item xs={12} md={6}>
            <Card elevation={1} sx={{ p: 3 }}>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2, display: "flex", alignItems: "center", gap: 1 }}>
                <Category fontSize="small" /> Classifier Playground
              </Typography>

              <TextField
                fullWidth
                multiline
                rows={4}
                label="Text to classify"
                placeholder="Enter the text you want to classify..."
                value={sequence}
                onChange={(e) => setSequence(e.target.value)}
                sx={{ mb: 2 }}
              />

              <TextField
                fullWidth
                label="Labels"
                placeholder="billing, technical, sales, general"
                helperText="Comma-separated list of candidate labels"
                value={labelsText}
                onChange={(e) => setLabelsText(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") handleClassify(); }}
                sx={{ mb: 2 }}
              />

              <Button
                variant="contained"
                onClick={handleClassify}
                disabled={loading || !sequence.trim() || !labelsText.trim()}
                fullWidth
              >
                {loading ? "Classifying..." : "Classify"}
              </Button>
            </Card>
          </Grid>

          {/* Results */}
          <Grid item xs={12} md={6}>
            <Card elevation={1} sx={{ p: 3 }}>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
                Results
              </Typography>

              {loading && <LinearProgress sx={{ mb: 2 }} />}

              {!results && !loading && (
                <Box sx={{ textAlign: "center", py: 6, color: "text.secondary" }}>
                  <Category sx={{ fontSize: 48, opacity: 0.2, mb: 1 }} />
                  <Typography variant="body2">Enter text and labels, then click Classify</Typography>
                </Box>
              )}

              {results && (
                <Box>
                  <Box sx={{ mb: 3, p: 2, bgcolor: "action.hover", borderRadius: 1 }}>
                    <Typography variant="caption" color="text.secondary">Input</Typography>
                    <Typography variant="body2" sx={{ fontStyle: "italic" }}>
                      {results.sequence}
                    </Typography>
                  </Box>

                  <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
                    {results.labels.map((label, i) => {
                      const score = results.scores[i];
                      const pct = (score * 100).toFixed(1);
                      return (
                        <Box key={label}>
                          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 0.5 }}>
                            <Chip
                              label={label}
                              size="small"
                              sx={{
                                bgcolor: COLORS[i % COLORS.length] + "20",
                                color: COLORS[i % COLORS.length],
                                fontWeight: i === 0 ? 700 : 400,
                                border: i === 0 ? `2px solid ${COLORS[i % COLORS.length]}` : "none",
                              }}
                            />
                            <Typography variant="body2" fontWeight={i === 0 ? 700 : 400}>
                              {pct}%
                            </Typography>
                          </Box>
                          <LinearProgress
                            variant="determinate"
                            value={score * 100}
                            sx={{
                              height: 8,
                              borderRadius: 4,
                              bgcolor: "action.hover",
                              "& .MuiLinearProgress-bar": {
                                bgcolor: COLORS[i % COLORS.length],
                                borderRadius: 4,
                              },
                            }}
                          />
                        </Box>
                      );
                    })}
                  </Box>

                  {results.labels.length > 0 && (
                    <Box sx={{ mt: 3, p: 2, bgcolor: COLORS[0] + "10", borderRadius: 1, border: `1px solid ${COLORS[0]}30` }}>
                      <Typography variant="body2" color="text.secondary">
                        Best match: <strong style={{ color: COLORS[0] }}>{results.labels[0]}</strong> ({(results.scores[0] * 100).toFixed(1)}%)
                      </Typography>
                    </Box>
                  )}
                </Box>
              )}
            </Card>
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
