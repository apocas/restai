import { useState, useEffect, Fragment } from "react";
import {
  Box, Button, Card, Chip, Divider, Grid, IconButton, Typography,
  TextField, Dialog, DialogTitle, DialogContent, DialogActions,
  Table, TableBody, TableCell, TableHead, TableRow,
  FormControl, FormGroup, FormControlLabel, Checkbox, CircularProgress,
  Collapse,
} from "@mui/material";
import {
  Add, Delete, PlayArrow, ExpandMore, ExpandLess, Science,
} from "@mui/icons-material";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const METRIC_COLORS = {
  answer_relevancy: "#3498db",
  faithfulness: "#2ecc71",
  correctness: "#e74c3c",
};

const STATUS_COLORS = {
  pending: "default",
  running: "info",
  completed: "success",
  failed: "error",
};

export default function ProjectEvals({ project }) {
  const auth = useAuth();
  const [datasets, setDatasets] = useState([]);
  const [runs, setRuns] = useState([]);
  const [selectedDataset, setSelectedDataset] = useState(null);
  const [selectedRun, setSelectedRun] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [addCaseOpen, setAddCaseOpen] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [newDataset, setNewDataset] = useState({ name: "", description: "" });
  const [newCase, setNewCase] = useState({ question: "", expected_answer: "" });
  const [runMetrics, setRunMetrics] = useState(["answer_relevancy"]);
  const [runDatasetId, setRunDatasetId] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchDatasets = () => {
    api.get(`/projects/${project.id}/evals/datasets`, auth.user.token)
      .then(setDatasets)
      .catch(() => {});
  };

  const fetchRuns = () => {
    api.get(`/projects/${project.id}/evals/runs`, auth.user.token)
      .then(setRuns)
      .catch(() => {});
  };

  const fetchDatasetDetail = (id) => {
    api.get(`/projects/${project.id}/evals/datasets/${id}`, auth.user.token)
      .then(setSelectedDataset)
      .catch(() => {});
  };

  const fetchRunDetail = (id) => {
    api.get(`/projects/${project.id}/evals/runs/${id}`, auth.user.token)
      .then(setSelectedRun)
      .catch(() => {});
  };

  useEffect(() => {
    fetchDatasets();
    fetchRuns();
  }, [project.id]);

  // Poll running evals
  useEffect(() => {
    const running = runs.some(r => r.status === "running" || r.status === "pending");
    if (!running) return;
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, [runs]);

  const handleCreateDataset = () => {
    api.post(`/projects/${project.id}/evals/datasets`, newDataset, auth.user.token)
      .then((created) => {
        setCreateOpen(false);
        setNewDataset({ name: "", description: "" });
        fetchDatasets();
        // Auto-select the new dataset so user can add cases immediately
        if (created && created.id) {
          fetchDatasetDetail(created.id);
        }
      })
      .catch(() => {});
  };

  const handleDeleteDataset = (id) => {
    if (!window.confirm("Delete this dataset and all its test cases?")) return;
    api.delete(`/projects/${project.id}/evals/datasets/${id}`, auth.user.token)
      .then(() => {
        fetchDatasets();
        if (selectedDataset?.id === id) setSelectedDataset(null);
      })
      .catch(() => {});
  };

  const handleAddCase = () => {
    api.post(`/projects/${project.id}/evals/datasets/${selectedDataset.id}/cases`, newCase, auth.user.token)
      .then(() => {
        setAddCaseOpen(false);
        setNewCase({ question: "", expected_answer: "" });
        fetchDatasetDetail(selectedDataset.id);
      })
      .catch(() => {});
  };

  const handleDeleteCase = (caseId) => {
    api.delete(`/projects/${project.id}/evals/datasets/${selectedDataset.id}/cases/${caseId}`, auth.user.token)
      .then(() => fetchDatasetDetail(selectedDataset.id))
      .catch(() => {});
  };

  const handleStartRun = () => {
    setLoading(true);
    api.post(`/projects/${project.id}/evals/runs`, { dataset_id: runDatasetId, metrics: runMetrics }, auth.user.token)
      .then(() => {
        setRunOpen(false);
        fetchRuns();
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const handleDeleteRun = (id) => {
    if (!window.confirm("Delete this evaluation run?")) return;
    api.delete(`/projects/${project.id}/evals/runs/${id}`, auth.user.token)
      .then(() => {
        fetchRuns();
        if (selectedRun?.id === id) setSelectedRun(null);
      })
      .catch(() => {});
  };

  const toggleMetric = (metric) => {
    setRunMetrics(prev =>
      prev.includes(metric) ? prev.filter(m => m !== metric) : [...prev, metric]
    );
  };

  // Build chart data from completed runs
  const chartData = runs
    .filter(r => r.status === "completed" && r.summary)
    .reverse()
    .map(r => ({
      date: r.completed_at ? new Date(r.completed_at).toLocaleDateString() : r.id,
      ...r.summary,
    }));

  const chartMetrics = [...new Set(runs.flatMap(r => r.summary ? Object.keys(r.summary) : []))];

  return (
    <Grid container spacing={3}>
      {/* Datasets */}
      <Grid item xs={12} md={6}>
        <Card elevation={3}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 2 }}>
            <Box sx={{ display: "flex", alignItems: "center" }}>
              <Science sx={{ ml: 2 }} />
              <H4 sx={{ p: 2 }}>Datasets</H4>
            </Box>
            <Button size="small" startIcon={<Add />} onClick={() => setCreateOpen(true)}>
              New Dataset
            </Button>
          </Box>
          <Divider />
          {!selectedDataset && datasets.length > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ px: 2, pt: 1, display: "block" }}>
              Click a dataset to manage its test cases.
            </Typography>
          )}
          {datasets.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
              No datasets yet. Create one to start evaluating.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ pl: 2 }}>Name</TableCell>
                  <TableCell align="center">Cases</TableCell>
                  <TableCell align="right" sx={{ pr: 2 }}>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {datasets.map(d => (
                  <TableRow
                    key={d.id}
                    hover
                    selected={selectedDataset?.id === d.id}
                    onClick={() => fetchDatasetDetail(d.id)}
                    sx={{ cursor: "pointer" }}
                  >
                    <TableCell sx={{ pl: 2 }}>{d.name}</TableCell>
                    <TableCell align="center">{d.test_case_count}</TableCell>
                    <TableCell align="right" sx={{ pr: 2 }}>
                      <IconButton
                        size="small"
                        onClick={(e) => { e.stopPropagation(); setRunDatasetId(d.id); setRunOpen(true); }}
                      >
                        <PlayArrow fontSize="small" />
                      </IconButton>
                      <IconButton
                        size="small"
                        onClick={(e) => { e.stopPropagation(); handleDeleteDataset(d.id); }}
                      >
                        <Delete fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* Selected dataset test cases */}
        {selectedDataset && (
          <Card elevation={3} sx={{ mt: 2 }}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", pr: 2 }}>
              <H4 sx={{ p: 2 }}>{selectedDataset.name} — Test Cases</H4>
              <Button size="small" startIcon={<Add />} onClick={() => setAddCaseOpen(true)}>
                Add Case
              </Button>
            </Box>
            <Divider />
            {(!selectedDataset.test_cases || selectedDataset.test_cases.length === 0) ? (
              <Box sx={{ p: 2 }}>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                  No test cases yet. Add questions to evaluate your project.
                </Typography>
                <Button size="small" variant="outlined" startIcon={<Add />} onClick={() => setAddCaseOpen(true)}>
                  Add First Test Case
                </Button>
              </Box>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ pl: 2 }}>Question</TableCell>
                    <TableCell>Expected Answer</TableCell>
                    <TableCell align="right" sx={{ pr: 2 }}></TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {selectedDataset.test_cases.map(tc => (
                    <TableRow key={tc.id}>
                      <TableCell sx={{ pl: 2, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {tc.question}
                      </TableCell>
                      <TableCell sx={{ maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {tc.expected_answer || "—"}
                      </TableCell>
                      <TableCell align="right" sx={{ pr: 2 }}>
                        <IconButton size="small" onClick={() => handleDeleteCase(tc.id)}>
                          <Delete fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        )}
      </Grid>

      {/* Runs */}
      <Grid item xs={12} md={6}>
        <Card elevation={3}>
          <Box sx={{ display: "flex", alignItems: "center" }}>
            <Science sx={{ ml: 2 }} />
            <H4 sx={{ p: 2 }}>Evaluation Runs</H4>
          </Box>
          <Divider />
          {runs.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
              No runs yet. Select a dataset and click the play button to start.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ pl: 2 }}>Run</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Scores</TableCell>
                  <TableCell align="right" sx={{ pr: 2 }}></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {runs.map(r => (
                  <TableRow
                    key={r.id}
                    hover
                    selected={selectedRun?.id === r.id}
                    onClick={() => fetchRunDetail(r.id)}
                    sx={{ cursor: "pointer" }}
                  >
                    <TableCell sx={{ pl: 2 }}>
                      #{r.id}
                      {r.prompt_version_id && (
                        <Chip label={`v${r.prompt_version_id}`} size="small" variant="outlined" sx={{ ml: 0.5 }} />
                      )}
                    </TableCell>
                    <TableCell>
                      <Chip label={r.status} color={STATUS_COLORS[r.status] || "default"} size="small" />
                    </TableCell>
                    <TableCell>
                      {r.summary ? Object.entries(r.summary).map(([k, v]) => (
                        <Chip
                          key={k}
                          label={`${k}: ${(v * 100).toFixed(0)}%`}
                          size="small"
                          sx={{ mr: 0.5, backgroundColor: METRIC_COLORS[k] || "#999", color: "#fff" }}
                        />
                      )) : "—"}
                    </TableCell>
                    <TableCell align="right">
                      <IconButton
                        size="small"
                        onClick={(e) => { e.stopPropagation(); handleDeleteRun(r.id); }}
                      >
                        <Delete fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>

        {/* Score trend chart */}
        {chartData.length > 1 && (
          <Card elevation={3} sx={{ mt: 2 }}>
            <H4 sx={{ p: 2 }}>Score Trend</H4>
            <Divider />
            <Box sx={{ p: 2 }}>
              <ResponsiveContainer width="100%" height={250}>
                <LineChart data={chartData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis domain={[0, 1]} tickFormatter={(v) => `${(v * 100).toFixed(0)}%`} />
                  <Tooltip formatter={(v) => `${(v * 100).toFixed(1)}%`} />
                  <Legend />
                  {chartMetrics.map(m => (
                    <Line key={m} type="monotone" dataKey={m} stroke={METRIC_COLORS[m] || "#999"} strokeWidth={2} dot />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </Box>
          </Card>
        )}

        {/* Selected run results */}
        {selectedRun && selectedRun.results && (
          <Card elevation={3} sx={{ mt: 2 }}>
            <H4 sx={{ p: 2 }}>Run #{selectedRun.id} Results</H4>
            <Divider />
            {selectedRun.error && (
              <Typography variant="body2" color="error" sx={{ p: 2 }}>{selectedRun.error}</Typography>
            )}
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ pl: 2 }}>Answer</TableCell>
                  <TableCell>Metric</TableCell>
                  <TableCell align="center">Score</TableCell>
                  <TableCell>Reason</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {selectedRun.results.map(r => (
                  <TableRow key={r.id}>
                    <TableCell sx={{ pl: 2, maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {r.actual_answer ? r.actual_answer.substring(0, 80) + (r.actual_answer.length > 80 ? "..." : "") : "—"}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={r.metric_name}
                        size="small"
                        sx={{ backgroundColor: METRIC_COLORS[r.metric_name] || "#999", color: "#fff" }}
                      />
                    </TableCell>
                    <TableCell align="center">
                      <Typography
                        variant="body2"
                        color={r.passed ? "success.main" : "error.main"}
                        fontWeight="bold"
                      >
                        {r.score !== null ? `${(r.score * 100).toFixed(0)}%` : "—"}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ pr: 2, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {r.reason || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
      </Grid>

      {/* Create Dataset Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>New Evaluation Dataset</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense" label="Name"
            value={newDataset.name}
            onChange={(e) => setNewDataset({ ...newDataset, name: e.target.value })}
          />
          <TextField
            fullWidth margin="dense" label="Description" multiline rows={2}
            value={newDataset.description}
            onChange={(e) => setNewDataset({ ...newDataset, description: e.target.value })}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreateDataset} disabled={!newDataset.name}>Create</Button>
        </DialogActions>
      </Dialog>

      {/* Add Test Case Dialog */}
      <Dialog open={addCaseOpen} onClose={() => setAddCaseOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Test Case</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense" label="Question" multiline rows={3}
            value={newCase.question}
            onChange={(e) => setNewCase({ ...newCase, question: e.target.value })}
          />
          <TextField
            fullWidth margin="dense" label="Expected Answer (optional)" multiline rows={3}
            value={newCase.expected_answer}
            onChange={(e) => setNewCase({ ...newCase, expected_answer: e.target.value })}
            helperText="Provide a ground truth answer to enable the 'correctness' metric"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAddCaseOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAddCase} disabled={!newCase.question}>Add</Button>
        </DialogActions>
      </Dialog>

      {/* Run Evaluation Dialog */}
      <Dialog open={runOpen} onClose={() => setRunOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Run Evaluation</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 2 }}>
            Select which metrics to evaluate. Each test case will be scored per metric.
          </Typography>
          <FormControl component="fieldset">
            <FormGroup>
              <FormControlLabel
                control={<Checkbox checked={runMetrics.includes("answer_relevancy")} onChange={() => toggleMetric("answer_relevancy")} />}
                label="Answer Relevancy — Is the answer relevant to the question?"
              />
              <FormControlLabel
                control={<Checkbox checked={runMetrics.includes("faithfulness")} onChange={() => toggleMetric("faithfulness")} />}
                label="Faithfulness — Is the answer grounded in retrieved context? (RAG only)"
              />
              <FormControlLabel
                control={<Checkbox checked={runMetrics.includes("correctness")} onChange={() => toggleMetric("correctness")} />}
                label="Correctness — Does the answer match the expected answer?"
              />
            </FormGroup>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRunOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleStartRun}
            disabled={loading || runMetrics.length === 0}
            startIcon={loading ? <CircularProgress size={16} /> : <PlayArrow />}
          >
            {loading ? "Starting..." : "Start"}
          </Button>
        </DialogActions>
      </Dialog>
    </Grid>
  );
}
