import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  Grid, IconButton, MenuItem, Switch, TextField, Tooltip, Typography,
  CircularProgress, FormControlLabel,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import AddIcon from "@mui/icons-material/Add";
import ScheduleIcon from "@mui/icons-material/Schedule";
import TimerIcon from "@mui/icons-material/Timer";
import HistoryIcon from "@mui/icons-material/History";
import {
  Table, TableBody, TableCell, TableHead, TableRow,
} from "@mui/material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const SCHEDULE_PRESETS = [
  { value: 1, label: "Every minute" },
  { value: 5, label: "Every 5 minutes" },
  { value: 15, label: "Every 15 minutes" },
  { value: 30, label: "Every 30 minutes" },
  { value: 60, label: "Every hour" },
  { value: 360, label: "Every 6 hours" },
  { value: 720, label: "Every 12 hours" },
  { value: 1440, label: "Every 24 hours" },
  { value: 10080, label: "Every 7 days" },
];

function formatSchedule(minutes) {
  const preset = SCHEDULE_PRESETS.find((p) => p.value === minutes);
  if (preset) return preset.label;
  if (minutes < 60) return `Every ${minutes} min`;
  if (minutes < 1440) return `Every ${Math.round(minutes / 60)} hr`;
  return `Every ${Math.round(minutes / 1440)} day(s)`;
}

export default function ProjectEditRoutines({ project }) {
  const { t } = useTranslation();
  const [routines, setRoutines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editRoutine, setEditRoutine] = useState(null);
  const [firingId, setFiringId] = useState(null);
  // History dialog: the routine whose log we're viewing + the fetched rows.
  const [historyTarget, setHistoryTarget] = useState(null);
  const [historyRuns, setHistoryRuns] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  const openHistory = (routine) => {
    setHistoryTarget(routine);
    setHistoryRuns([]);
    setHistoryLoading(true);
    api.get(`/projects/${project.id}/routines/${routine.id}/history?limit=50`, auth.user.token)
      .then((d) => setHistoryRuns(d.runs || []))
      .catch(() => {})
      .finally(() => setHistoryLoading(false));
  };
  const [form, setForm] = useState({ name: "", message: "", schedule_minutes: 60, enabled: true });
  const auth = useAuth();
  const serverUrl = process.env.REACT_APP_RESTAI_API_URL || window.location.origin;

  const fetchRoutines = () => {
    if (!project?.id) return;
    setLoading(true);
    api.get(`/projects/${project.id}/routines`, auth.user.token)
      .then((d) => setRoutines(d.routines || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchRoutines();
  }, [project?.id]);

  const handleCreate = () => {
    api.post(`/projects/${project.id}/routines`, form, auth.user.token)
      .then(() => {
        toast.success("Routine created");
        setCreateOpen(false);
        setForm({ name: "", message: "", schedule_minutes: 60, enabled: true });
        fetchRoutines();
      })
      .catch(() => {});
  };

  const handleUpdate = () => {
    if (!editRoutine) return;
    api.patch(`/projects/${project.id}/routines/${editRoutine.id}`, {
      name: editRoutine.name,
      message: editRoutine.message,
      schedule_minutes: editRoutine.schedule_minutes,
      enabled: editRoutine.enabled,
    }, auth.user.token)
      .then(() => {
        toast.success("Routine updated");
        setEditRoutine(null);
        fetchRoutines();
      })
      .catch(() => {});
  };

  const handleDelete = (routine) => {
    if (!window.confirm(`Delete routine "${routine.name}"?`)) return;
    api.delete(`/projects/${project.id}/routines/${routine.id}`, auth.user.token)
      .then(() => {
        toast.success("Routine deleted");
        fetchRoutines();
      })
      .catch(() => {});
  };

  const handleToggle = (routine) => {
    api.patch(`/projects/${project.id}/routines/${routine.id}`, { enabled: !routine.enabled }, auth.user.token)
      .then(() => fetchRoutines())
      .catch(() => {});
  };

  const handleFire = (routine) => {
    setFiringId(routine.id);
    api.post(`/projects/${project.id}/routines/${routine.id}/fire`, {}, auth.user.token)
      .then((d) => {
        toast.success("Routine fired");
        fetchRoutines();
      })
      .catch(() => {})
      .finally(() => setFiringId(null));
  };

  if (loading) return <Box sx={{ textAlign: "center", py: 4 }}><CircularProgress size={24} /></Box>;

  return (
    <Card elevation={1} sx={{ p: 3 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
        <Typography sx={{ fontWeight: 600, fontSize: "0.9rem", display: "flex", alignItems: "center", gap: 0.5, color: "text.secondary" }}>
          <TimerIcon fontSize="small" /> Routines
        </Typography>
        <Button variant="outlined" size="small" startIcon={<AddIcon />} onClick={() => setCreateOpen(true)}>
          Add Routine
        </Button>
      </Box>
      <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 2 }}>
        Scheduled messages that fire automatically at set intervals.
      </Typography>

      {routines.length === 0 ? (
        <Typography variant="body2" color="textSecondary" sx={{ textAlign: "center", py: 3 }}>
          No routines yet. Create one to schedule automated behaviour.
        </Typography>
      ) : (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
          {routines.map((r) => (
            <Card
              key={r.id}
              variant="outlined"
              sx={{
                p: 2,
                borderRadius: 2,
                opacity: r.enabled ? 1 : 0.5,
              }}
            >
              <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 2 }}>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                    <Typography variant="body2" fontWeight={600}>{r.name}</Typography>
                    <Chip label={`#${r.id}`} size="small" variant="outlined" sx={{ height: 18, fontSize: "0.65rem", fontFamily: "monospace" }} />
                    <Chip
                      label={r.enabled ? "Active" : "Disabled"}
                      size="small"
                      color={r.enabled ? "success" : "default"}
                      variant="outlined"
                      sx={{ height: 20, fontSize: "0.68rem", cursor: "pointer" }}
                      onClick={() => handleToggle(r)}
                    />
                    <Chip
                      icon={<ScheduleIcon sx={{ fontSize: 14 }} />}
                      label={formatSchedule(r.schedule_minutes)}
                      size="small"
                      variant="outlined"
                      sx={{ height: 20, fontSize: "0.68rem" }}
                    />
                  </Box>
                  <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 0.5 }}>
                    {r.message.length > 120 ? r.message.substring(0, 120) + "..." : r.message}
                  </Typography>
                  {r.last_run && (
                    <Typography variant="caption" color="textSecondary" sx={{ display: "block" }}>
                      Last run: {new Date(r.last_run).toLocaleString()}
                      {r.last_result && (
                        <span> — {r.last_result.substring(0, 80)}{r.last_result.length > 80 ? "..." : ""}</span>
                      )}
                    </Typography>
                  )}
                </Box>
                <Box sx={{ display: "flex", gap: 0.5, flexShrink: 0 }}>
                  <Tooltip title={t("projects.edit.routines.fireNow")}>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={() => handleFire(r)}
                      disabled={firingId === r.id}
                    >
                      {firingId === r.id ? <CircularProgress size={18} /> : <PlayArrowIcon fontSize="small" />}
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t("projects.edit.routines.history")}>
                    <IconButton size="small" onClick={() => openHistory(r)}>
                      <HistoryIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t("projects.actions.edit")}>
                    <IconButton size="small" onClick={() => setEditRoutine({ ...r })}>
                      <EditIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t("projects.actions.delete")}>
                    <IconButton size="small" color="error" onClick={() => handleDelete(r)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Box>
            </Card>
          ))}
        </Box>
      )}

      {/* Create Dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create Routine</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <TextField
                fullWidth size="small" label="Name"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="e.g. Daily health check"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                fullWidth size="small" label="Message" multiline minRows={3}
                value={form.message}
                onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder="The message to send to the project"
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth select size="small" label="Schedule"
                value={form.schedule_minutes}
                onChange={(e) => setForm({ ...form, schedule_minutes: parseInt(e.target.value) })}
              >
                {SCHEDULE_PRESETS.map((p) => (
                  <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <FormControlLabel
                control={<Switch checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />}
                label="Enabled"
              />
            </Grid>
          </Grid>
          <Box sx={{ mt: 2, p: 1.5, borderRadius: 1, backgroundColor: (t) => t.palette.mode === "dark" ? "#0f0f17" : "#f5f5f5" }}>
            <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 0.5 }}>
              Fire via API (after creation, use the routine ID from the list):
            </Typography>
            <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.75rem", wordBreak: "break-all" }}>
              curl -X POST {serverUrl}/projects/{project.id}/routines/&#123;routineId&#125;/fire -H "Authorization: Bearer YOUR_API_KEY"
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate} disabled={!form.name.trim() || !form.message.trim()}>
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Dialog */}
      {editRoutine && (
        <Dialog open onClose={() => setEditRoutine(null)} maxWidth="sm" fullWidth>
          <DialogTitle>Edit Routine</DialogTitle>
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid item xs={12}>
                <TextField
                  fullWidth size="small" label="Name"
                  value={editRoutine.name}
                  onChange={(e) => setEditRoutine({ ...editRoutine, name: e.target.value })}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth size="small" label="Message" multiline minRows={3}
                  value={editRoutine.message}
                  onChange={(e) => setEditRoutine({ ...editRoutine, message: e.target.value })}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth select size="small" label="Schedule"
                  value={editRoutine.schedule_minutes}
                  onChange={(e) => setEditRoutine({ ...editRoutine, schedule_minutes: parseInt(e.target.value) })}
                >
                  {SCHEDULE_PRESETS.map((p) => (
                    <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid item xs={12} sm={6}>
                <FormControlLabel
                  control={<Switch checked={editRoutine.enabled} onChange={(e) => setEditRoutine({ ...editRoutine, enabled: e.target.checked })} />}
                  label="Enabled"
                />
              </Grid>
            </Grid>
            <Box sx={{ mt: 2, p: 1.5, borderRadius: 1, backgroundColor: (t) => t.palette.mode === "dark" ? "#0f0f17" : "#f5f5f5" }}>
              <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 0.5 }}>
                Fire via API:
              </Typography>
              <Typography variant="caption" sx={{ fontFamily: "monospace", fontSize: "0.75rem", wordBreak: "break-all" }}>
                curl -X POST {serverUrl}/projects/{project.id}/routines/{editRoutine.id}/fire -H "Authorization: Bearer YOUR_API_KEY"
              </Typography>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditRoutine(null)}>Cancel</Button>
            <Button variant="contained" onClick={handleUpdate}>Save</Button>
          </DialogActions>
        </Dialog>
      )}

      {/* Execution history dialog */}
      <Dialog open={!!historyTarget} onClose={() => setHistoryTarget(null)} maxWidth="md" fullWidth>
        <DialogTitle>{t("projects.edit.routines.history")}: {historyTarget?.name}</DialogTitle>
        <DialogContent>
          {historyLoading ? (
            <Box sx={{ textAlign: "center", py: 3 }}><CircularProgress size={24} /></Box>
          ) : historyRuns.length === 0 ? (
            <Typography variant="body2" color="textSecondary" sx={{ py: 3, textAlign: "center" }}>
              No runs yet. Trigger with Fire or wait for the cron to pick this up.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>When</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Source</TableCell>
                  <TableCell align="right">Duration</TableCell>
                  <TableCell>Result</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {historyRuns.map((run) => (
                  <TableRow key={run.id}>
                    <TableCell sx={{ whiteSpace: "nowrap", fontSize: "0.8rem" }}>
                      {new Date(run.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <Chip size="small" label={run.status} color={run.status === "ok" ? "success" : "error"} />
                    </TableCell>
                    <TableCell>{run.manual ? "manual" : "cron"}</TableCell>
                    <TableCell align="right" sx={{ fontSize: "0.8rem" }}>
                      {run.duration_ms != null ? `${run.duration_ms} ms` : "—"}
                    </TableCell>
                    <TableCell sx={{ fontSize: "0.8rem", maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {run.result || ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => historyTarget && openHistory(historyTarget)} disabled={historyLoading}>{t("common.refresh")}</Button>
          <Button onClick={() => setHistoryTarget(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}
