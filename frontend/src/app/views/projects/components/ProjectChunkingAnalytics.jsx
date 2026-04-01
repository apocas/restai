import { useState, useEffect } from "react";
import {
  Alert, Box, Card, Chip, Divider, Grid, Typography, styled,
} from "@mui/material";
import { Analytics } from "@mui/icons-material";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from "recharts";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const SectionTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  fontSize: "0.9rem",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.5),
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1),
}));

const StatCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2),
  textAlign: "center",
}));

export default function ProjectChunkingAnalytics({ project }) {
  const auth = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!project.id || project.type !== "rag") return;
    api.get(`/projects/${project.id}/analytics/chunking?days=30`, auth.user.token, { silent: true })
      .then(setData)
      .catch(() => setData(null));
  }, [project.id]);

  if (!data) return null;

  const distData = data.size_distribution.buckets.map((b, i) => ({
    bucket: b,
    "All Chunks": data.size_distribution.counts[i] || 0,
    "Retrieved": data.retrieval_analysis.size_distribution.counts[i] || 0,
  }));

  const scoreData = data.retrieval_analysis.score_by_size
    .filter((s) => s.avg_score !== null)
    .map((s) => ({
      bucket: s.bucket,
      "Avg Score": s.avg_score,
      count: s.count,
    }));

  const severityMap = { high: "error", medium: "warning", info: "info" };

  return (
    <Card elevation={1} sx={{ p: 2.5 }}>
      <SectionTitle><Analytics fontSize="small" /> Chunk Analytics (Last 30 Days)</SectionTitle>

      {data.truncated && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Analysis limited to first 50,000 chunks. Results are approximate.
        </Alert>
      )}

      {/* Summary stats */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={6} sm={3}>
          <StatCard elevation={0} variant="outlined">
            <Typography variant="h6">{data.total_chunks}</Typography>
            <Typography variant="caption" color="text.secondary">Total Chunks</Typography>
          </StatCard>
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard elevation={0} variant="outlined">
            <Typography variant="h6">{data.avg_chunk_tokens}</Typography>
            <Typography variant="caption" color="text.secondary">Avg Chunk Tokens</Typography>
          </StatCard>
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard elevation={0} variant="outlined">
            <Typography variant="h6" color={data.retrieval_analysis.retrieval_rate < 0.3 ? "warning.main" : "success.main"}>
              {Math.round(data.retrieval_analysis.retrieval_rate * 100)}%
            </Typography>
            <Typography variant="caption" color="text.secondary">Retrieval Rate</Typography>
          </StatCard>
        </Grid>
        <Grid item xs={6} sm={3}>
          <StatCard elevation={0} variant="outlined">
            <Typography variant="h6">
              {data.retrieval_analysis.avg_score != null
                ? `${(data.retrieval_analysis.avg_score * 100).toFixed(0)}%`
                : "—"}
            </Typography>
            <Typography variant="caption" color="text.secondary">Avg Score</Typography>
          </StatCard>
        </Grid>
      </Grid>

      {/* Chunk Size Distribution */}
      {data.total_chunks > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Chunk Size Distribution (tokens)</Typography>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={distData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="bucket" fontSize={12} />
              <YAxis fontSize={12} />
              <Tooltip />
              <Legend />
              <Bar dataKey="All Chunks" fill="#8884d8" />
              <Bar dataKey="Retrieved" fill="#82ca9d" />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}

      {/* Score by Chunk Size */}
      {scoreData.length > 0 && (
        <Box sx={{ mb: 3 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Avg Retrieval Score by Chunk Size</Typography>
          <ResponsiveContainer width="100%" height={200}>
            <BarChart data={scoreData}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="bucket" fontSize={12} />
              <YAxis domain={[0, 1]} fontSize={12} />
              <Tooltip formatter={(v) => `${(v * 100).toFixed(1)}%`} />
              <Bar dataKey="Avg Score" fill="#ffc658" />
            </BarChart>
          </ResponsiveContainer>
        </Box>
      )}

      {/* Recommendations */}
      {data.recommendations.length > 0 && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>Recommendations</Typography>
          {data.recommendations.map((rec, i) => (
            <Alert
              key={i}
              severity={severityMap[rec.severity] || "info"}
              sx={{ mb: 1 }}
              action={
                rec.suggested_chunk_size ? (
                  <Chip label={`${rec.suggested_chunk_size} tokens`} size="small" color="primary" variant="outlined" />
                ) : null
              }
            >
              {rec.message}
            </Alert>
          ))}
        </Box>
      )}

      {data.total_chunks === 0 && data.recommendations.length === 0 && (
        <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
          No chunks found. Ingest documents to start tracking chunk analytics.
        </Typography>
      )}
    </Card>
  );
}
