import { useState, useEffect } from "react";
import {
  Box, Card, Chip, Divider, Grid, Typography, styled,
  Table, TableBody, TableCell, TableHead, TableRow,
  LinearProgress,
} from "@mui/material";
import { Storage } from "@mui/icons-material";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

const StatCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2),
  textAlign: "center",
}));

export default function ProjectSourceAnalytics({ project }) {
  const auth = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    if (!project.id || project.type !== "rag") return;
    api.get(`/projects/${project.id}/analytics/sources?days=30`, auth.user.token, { silent: true })
      .then(setData)
      .catch(() => setData(null));
  }, [project.id]);

  if (!data) return null;

  const maxRetrievals = data.sources.length > 0 ? data.sources[0].retrievals : 1;
  const totalRetrievals = data.sources.reduce((sum, s) => sum + s.retrievals, 0);

  return (
    <Card elevation={3}>
      <FlexBox>
        <Storage sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>Source Analytics (Last 30 Days)</H4>
      </FlexBox>
      <Divider />

      <Box sx={{ p: 2 }}>
        {/* Summary */}
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={4}>
            <StatCard elevation={1}>
              <Typography variant="h6">{data.sources.length}</Typography>
              <Typography variant="caption" color="text.secondary">Active Sources</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={4}>
            <StatCard elevation={1}>
              <Typography variant="h6">{totalRetrievals}</Typography>
              <Typography variant="caption" color="text.secondary">Total Retrievals</Typography>
            </StatCard>
          </Grid>
          <Grid item xs={4}>
            <StatCard elevation={1}>
              <Typography variant="h6" color={data.never_retrieved.length > 0 ? "warning.main" : "success.main"}>
                {data.never_retrieved.length}
              </Typography>
              <Typography variant="caption" color="text.secondary">Never Retrieved</Typography>
            </StatCard>
          </Grid>
        </Grid>

        {/* Source retrieval table */}
        {data.sources.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mb: 1 }}>Retrieval Frequency</Typography>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ pl: 2 }}>Source</TableCell>
                  <TableCell align="center">Retrievals</TableCell>
                  <TableCell align="center">Avg Score</TableCell>
                  <TableCell sx={{ pr: 2, width: "30%" }}></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.sources.map((s) => (
                  <TableRow key={s.source}>
                    <TableCell sx={{ pl: 2, maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {s.source}
                    </TableCell>
                    <TableCell align="center">{s.retrievals}</TableCell>
                    <TableCell align="center">
                      <Chip
                        label={`${(s.avg_score * 100).toFixed(0)}%`}
                        size="small"
                        color={s.avg_score >= 0.7 ? "success" : s.avg_score >= 0.4 ? "warning" : "error"}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell sx={{ pr: 2 }}>
                      <LinearProgress
                        variant="determinate"
                        value={(s.retrievals / maxRetrievals) * 100}
                        sx={{ height: 8, borderRadius: 4 }}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}

        {/* Never retrieved */}
        {data.never_retrieved.length > 0 && (
          <>
            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }} color="warning.main">
              Never Retrieved ({data.never_retrieved.length})
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
              These documents have not been retrieved in any query in the last 30 days. Consider reviewing or removing them.
            </Typography>
            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
              {data.never_retrieved.map((name) => (
                <Chip key={name} label={name} size="small" variant="outlined" color="warning" />
              ))}
            </Box>
          </>
        )}

        {data.sources.length === 0 && data.never_retrieved.length === 0 && (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
            No retrieval data yet. Query the project to start tracking source usage.
          </Typography>
        )}
      </Box>
    </Card>
  );
}
