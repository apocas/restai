import React, { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, CircularProgress, Collapse, Divider, styled, Typography,
  Table, TableBody, TableCell, TableHead, TableRow,
  TextField, MenuItem, IconButton,
} from "@mui/material";
import ScheduleIcon from "@mui/icons-material/Schedule";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import DeleteSweepIcon from "@mui/icons-material/DeleteSweep";
import ChevronLeftIcon from "@mui/icons-material/ChevronLeft";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import Breadcrumb from "app/components/Breadcrumb";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

const STATUS_COLORS = {
  success: "success",
  error: "error",
  warning: "warning",
};

const JOBS = ["sync", "telegram", "docker_cleanup", "routines"];

export default function CronLogs() {
  const auth = useAuth();
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [filterJob, setFilterJob] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [expandedId, setExpandedId] = useState(null);
  const [running, setRunning] = useState(false);
  const pageSize = 25;

  const fetchEntries = () => {
    const params = new URLSearchParams({
      start: page * pageSize,
      end: (page + 1) * pageSize,
    });
    if (filterJob) params.set("job", filterJob);
    if (filterStatus) params.set("status", filterStatus);

    api.get("/cron-logs?" + params.toString(), auth.user.token, { silent: true })
      .then((data) => {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      })
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Cron Logs";
    fetchEntries();
  }, [page, filterJob, filterStatus]);

  const totalPages = Math.ceil(total / pageSize);

  const handleRunNow = () => {
    setRunning(true);
    api.post("/cron-logs/run", {}, auth.user.token)
      .then(() => {
        setTimeout(() => {
          fetchEntries();
          setRunning(false);
        }, 3000);
      })
      .catch(() => setRunning(false));
  };

  const formatDuration = (ms) => {
    if (ms == null) return "—";
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Cron Logs", path: "/admin/cron-logs" }]} />
      </Box>

      <ContentBox>
        <Card elevation={3}>
          <FlexBox justifyContent="space-between" sx={{ pr: 2 }}>
            <FlexBox>
              <ScheduleIcon sx={{ ml: 2 }} />
              <H4 sx={{ p: 2 }}>Cron Logs</H4>
              <Typography variant="caption" color="text.secondary">
                {total} entries
              </Typography>
            </FlexBox>
            <FlexBox sx={{ gap: 1 }}>
              <Button
                variant="contained"
                size="small"
                startIcon={running ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
                disabled={running}
                onClick={handleRunNow}
              >
                {running ? "Running..." : "Run Now"}
              </Button>
              <Button
                variant="outlined"
                size="small"
                color="error"
                startIcon={<DeleteSweepIcon />}
                onClick={() => {
                  if (window.confirm("Purge all cron log entries?")) {
                    api.delete("/cron-logs", auth.user.token)
                      .then(() => { setPage(0); fetchEntries(); })
                      .catch(() => {});
                  }
                }}
              >
                Purge
              </Button>
              <TextField
                select
                size="small"
                label="Job"
                value={filterJob}
                onChange={(e) => { setFilterJob(e.target.value); setPage(0); }}
                sx={{ width: 160 }}
              >
                <MenuItem value="">All</MenuItem>
                {JOBS.map((j) => (
                  <MenuItem key={j} value={j}>{j}</MenuItem>
                ))}
              </TextField>
              <TextField
                select
                size="small"
                label="Status"
                value={filterStatus}
                onChange={(e) => { setFilterStatus(e.target.value); setPage(0); }}
                sx={{ width: 120 }}
              >
                <MenuItem value="">All</MenuItem>
                <MenuItem value="success">Success</MenuItem>
                <MenuItem value="error">Error</MenuItem>
                <MenuItem value="warning">Warning</MenuItem>
              </TextField>
            </FlexBox>
          </FlexBox>
          <Divider />

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ pl: 2, width: 40 }} />
                <TableCell>Date</TableCell>
                <TableCell>Job</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Message</TableCell>
                <TableCell align="center">Items</TableCell>
                <TableCell align="right" sx={{ pr: 2 }}>Duration</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center" sx={{ py: 4 }}>
                    <Typography variant="body2" color="text.secondary">No cron log entries found</Typography>
                  </TableCell>
                </TableRow>
              ) : (
                entries.map((e) => (
                  <React.Fragment key={e.id}>
                    <TableRow
                      hover
                      sx={{ cursor: "pointer" }}
                      onClick={() => setExpandedId(expandedId === e.id ? null : e.id)}
                    >
                      <TableCell sx={{ pl: 2, width: 40 }}>
                        <IconButton size="small">
                          {expandedId === e.id ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                        </IconButton>
                      </TableCell>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>
                        {e.date ? new Date(e.date).toLocaleString() : ""}
                      </TableCell>
                      <TableCell>
                        <Chip label={e.job} size="small" variant="outlined" />
                      </TableCell>
                      <TableCell>
                        <Chip
                          label={e.status}
                          size="small"
                          color={STATUS_COLORS[e.status] || "default"}
                          variant="outlined"
                        />
                      </TableCell>
                      <TableCell sx={{ maxWidth: 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {e.message || "—"}
                      </TableCell>
                      <TableCell align="center">{e.items_processed || 0}</TableCell>
                      <TableCell align="right" sx={{ pr: 2 }}>{formatDuration(e.duration_ms)}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell colSpan={7} sx={{ py: 0, borderBottom: expandedId === e.id ? undefined : "none" }}>
                        <Collapse in={expandedId === e.id}>
                          <Box sx={{ p: 2 }}>
                            <Typography variant="subtitle2" gutterBottom>Message</Typography>
                            <Box
                              component="pre"
                              sx={{
                                bgcolor: "grey.100",
                                p: 2,
                                borderRadius: 1,
                                overflow: "auto",
                                maxHeight: 300,
                                fontSize: "0.8rem",
                                whiteSpace: "pre-wrap",
                                wordBreak: "break-all",
                              }}
                            >
                              {e.message || "No output"}
                            </Box>
                            {e.details && (
                              <Box sx={{ mt: 2 }}>
                                <Typography variant="subtitle2" gutterBottom>Details</Typography>
                                <Box
                                  component="pre"
                                  sx={{
                                    bgcolor: "#fff3f3",
                                    p: 2,
                                    borderRadius: 1,
                                    overflow: "auto",
                                    maxHeight: 300,
                                    fontSize: "0.8rem",
                                    whiteSpace: "pre-wrap",
                                    wordBreak: "break-all",
                                  }}
                                >
                                  {e.details}
                                </Box>
                              </Box>
                            )}
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </React.Fragment>
                ))
              )}
            </TableBody>
          </Table>

          {totalPages > 1 && (
            <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", p: 2, gap: 1 }}>
              <IconButton onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0} size="small">
                <ChevronLeftIcon />
              </IconButton>
              <Typography variant="body2">
                Page {page + 1} of {totalPages}
              </Typography>
              <IconButton onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1} size="small">
                <ChevronRightIcon />
              </IconButton>
            </Box>
          )}
        </Card>
      </ContentBox>
    </Container>
  );
}
