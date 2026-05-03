import React, { useState, useEffect } from "react";
import {
  Box, Card, Chip, CircularProgress, Divider, styled, Switch, Typography,
  Table, TableBody, TableCell, TableHead, TableRow, IconButton, Tooltip,
} from "@mui/material";
import ScheduleIcon from "@mui/icons-material/Schedule";
import RefreshIcon from "@mui/icons-material/Refresh";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import { Link as RouterLink } from "react-router-dom";
import Breadcrumb from "app/components/Breadcrumb";
import { H4 } from "app/components/Typography";
import { useTranslation } from "react-i18next";
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

// Render minutes as "1h 30m", "45m", "2d", etc. Keeps the column tight
// without losing precision for both short (5 min poll) and long (daily)
// schedules.
function formatInterval(mins) {
  if (mins == null) return "—";
  if (mins < 60) return `${mins}m`;
  if (mins < 60 * 24) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    return m === 0 ? `${h}h` : `${h}h ${m}m`;
  }
  const d = Math.floor(mins / (60 * 24));
  const h = Math.floor((mins % (60 * 24)) / 60);
  return h === 0 ? `${d}d` : `${d}d ${h}h`;
}

export default function Routines() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [routines, setRoutines] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pendingId, setPendingId] = useState(null);

  const fetchRoutines = () => {
    setLoading(true);
    api.get("/admin/routines", auth.user.token, { silent: true })
      .then((data) => setRoutines(data.routines || []))
      .catch(() => setRoutines([]))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("routines.title");
    fetchRoutines();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const handleToggle = (r) => {
    const next = !r.enabled;
    // Optimistic flip — revert on failure so the UI never lies.
    setRoutines((cur) => cur.map((x) => (x.id === r.id ? { ...x, enabled: next } : x)));
    setPendingId(r.id);
    api.patch(`/admin/routines/${r.id}`, { enabled: next }, auth.user.token)
      .catch(() => {
        setRoutines((cur) => cur.map((x) => (x.id === r.id ? { ...x, enabled: !next } : x)));
      })
      .finally(() => setPendingId(null));
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("routines.title"), path: "/admin/routines" }]} />
      </Box>

      <ContentBox>
        <Card elevation={3}>
          <FlexBox justifyContent="space-between" sx={{ pr: 2 }}>
            <FlexBox>
              <ScheduleIcon sx={{ ml: 2 }} />
              <H4 sx={{ p: 2 }}>{t("routines.title")}</H4>
              <Typography variant="caption" color="text.secondary">
                {t("routines.entries", { count: routines.length })}
              </Typography>
            </FlexBox>
            <FlexBox>
              <Tooltip title={t("routines.refresh")}>
                <span>
                  <IconButton onClick={fetchRoutines} disabled={loading} size="small">
                    {loading ? <CircularProgress size={18} /> : <RefreshIcon />}
                  </IconButton>
                </span>
              </Tooltip>
            </FlexBox>
          </FlexBox>
          <Divider />

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ pl: 2 }}>{t("routines.columns.project")}</TableCell>
                <TableCell>{t("routines.columns.name")}</TableCell>
                <TableCell align="center">{t("routines.columns.interval")}</TableCell>
                <TableCell sx={{ whiteSpace: "nowrap" }}>{t("routines.columns.lastRun")}</TableCell>
                <TableCell align="center" sx={{ pr: 2 }}>{t("routines.columns.enabled")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {routines.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 4 }}>
                    <Typography variant="body2" color="text.secondary">
                      {loading ? t("routines.loading") : t("routines.empty")}
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                routines.map((r) => (
                  <TableRow hover key={r.id}>
                    <TableCell sx={{ pl: 2 }}>
                      <FlexBox sx={{ gap: 0.5 }}>
                        <RouterLink
                          to={`/project/${r.project_id}/edit`}
                          style={{ color: "inherit", textDecoration: "none" }}
                        >
                          {r.project_name}
                        </RouterLink>
                        <Tooltip title={t("routines.openProject")}>
                          <IconButton
                            component={RouterLink}
                            to={`/project/${r.project_id}/edit`}
                            size="small"
                          >
                            <OpenInNewIcon fontSize="inherit" />
                          </IconButton>
                        </Tooltip>
                        <Chip label={r.project_type} size="small" variant="outlined" sx={{ ml: 0.5 }} />
                      </FlexBox>
                    </TableCell>
                    <TableCell>{r.name}</TableCell>
                    <TableCell align="center">{formatInterval(r.schedule_minutes)}</TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>
                      {r.last_run ? new Date(r.last_run).toLocaleString() : "—"}
                    </TableCell>
                    <TableCell align="center" sx={{ pr: 2 }}>
                      <Switch
                        checked={r.enabled}
                        disabled={pendingId === r.id}
                        onChange={() => handleToggle(r)}
                        size="small"
                      />
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Card>
      </ContentBox>
    </Container>
  );
}
