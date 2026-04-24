import { useState, useEffect, useMemo } from "react";
import {
  Box, Card, Chip, Divider, Grid, Typography, styled,
  Table, TableBody, TableCell, TableHead, TableRow,
  IconButton,
} from "@mui/material";
import { Security, ChevronLeft, ChevronRight } from "@mui/icons-material";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

const StatCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2),
  textAlign: "center",
}));

export default function ProjectGuards({ project }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [summary, setSummary] = useState(null);
  const [daily, setDaily] = useState([]);
  const [events, setEvents] = useState([]);
  const [eventsTotal, setEventsTotal] = useState(0);

  const now = new Date();
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);

  const monthLabel = new Date(selectedYear, selectedMonth - 1).toLocaleString("default", { month: "long", year: "numeric" });

  const handlePrev = () => {
    if (selectedMonth === 1) { setSelectedMonth(12); setSelectedYear(selectedYear - 1); }
    else setSelectedMonth(selectedMonth - 1);
  };
  const handleNext = () => {
    const cy = now.getFullYear(), cm = now.getMonth() + 1;
    if (selectedYear === cy && selectedMonth === cm) return;
    if (selectedMonth === 12) { setSelectedMonth(1); setSelectedYear(selectedYear + 1); }
    else setSelectedMonth(selectedMonth + 1);
  };

  useEffect(() => {
    api.get(`/projects/${project.id}/guards/summary`, auth.user.token, { silent: true })
      .then(setSummary)
      .catch(() => {});
    api.get(`/projects/${project.id}/guards/events?start=0&end=20&action=block`, auth.user.token, { silent: true })
      .then((d) => { setEvents(d.events || []); setEventsTotal(d.total || 0); })
      .catch(() => {});
  }, [project.id]);

  useEffect(() => {
    const params = new URLSearchParams({ year: selectedYear, month: selectedMonth });
    api.get(`/projects/${project.id}/guards/daily?${params}`, auth.user.token, { silent: true })
      .then((d) => setDaily(d.events || []))
      .catch(() => {});
  }, [project.id, selectedYear, selectedMonth]);

  const filledDaily = useMemo(() => {
    const daysInMonth = new Date(selectedYear, selectedMonth, 0).getDate();
    const map = {};
    daily.forEach((d) => { map[d.date] = d; });
    const result = [];
    for (let day = 1; day <= daysInMonth; day++) {
      const date = new Date(selectedYear, selectedMonth - 1, day);
      const dateStr = date.toISOString().split("T")[0];
      result.push(map[dateStr] || { date: dateStr, checks: 0, blocks: 0, warns: 0 });
    }
    return result;
  }, [daily, selectedYear, selectedMonth]);

  if (!summary) {
    return (
      <Card elevation={3} sx={{ p: 4, textAlign: "center" }}>
        <Security sx={{ fontSize: 48, opacity: 0.3, mb: 1 }} />
        <Typography variant="body2" color="text.secondary">
          {t("projects.knowledge.guardAnalytics.noData")}
        </Typography>
      </Card>
    );
  }

  return (
    <Grid container spacing={3}>
      {/* Summary */}
      <Grid item xs={12}>
        <Card elevation={3}>
          <FlexBox justifyContent="space-between">
            <FlexBox>
              <Security sx={{ ml: 2 }} />
              <H4 sx={{ p: 2 }}>{t("projects.knowledge.guardAnalytics.title")}</H4>
            </FlexBox>
            <FlexBox sx={{ mr: 2 }}>
              <IconButton onClick={handlePrev} size="small"><ChevronLeft /></IconButton>
              <Typography variant="subtitle1" sx={{ mx: 1, minWidth: 140, textAlign: "center" }}>{monthLabel}</Typography>
              <IconButton onClick={handleNext} size="small"><ChevronRight /></IconButton>
            </FlexBox>
          </FlexBox>
          <Divider />

          <Box sx={{ p: 2 }}>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={6} sm={3}>
                <StatCard elevation={1}>
                  <Typography variant="h6">{summary.total_checks.toLocaleString()}</Typography>
                  <Typography variant="caption" color="text.secondary">{t("projects.knowledge.guardAnalytics.totalChecks")}</Typography>
                </StatCard>
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatCard elevation={1}>
                  <Typography variant="h6" color="error.main">{summary.total_blocks}</Typography>
                  <Typography variant="caption" color="text.secondary">{t("projects.knowledge.guardAnalytics.blocked")}</Typography>
                </StatCard>
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatCard elevation={1}>
                  <Typography variant="h6">{(summary.block_rate * 100).toFixed(1)}%</Typography>
                  <Typography variant="caption" color="text.secondary">{t("projects.knowledge.guardAnalytics.blockRate")}</Typography>
                </StatCard>
              </Grid>
              <Grid item xs={6} sm={3}>
                <StatCard elevation={1}>
                  <Typography variant="h6" color="warning.main">{summary.warn_count}</Typography>
                  <Typography variant="caption" color="text.secondary">{t("projects.knowledge.guardAnalytics.warnings")}</Typography>
                </StatCard>
              </Grid>
            </Grid>

            <Typography variant="subtitle2" sx={{ mb: 1 }}>{t("projects.knowledge.guardAnalytics.events")}</Typography>
            <ResponsiveContainer width="100%" height={250}>
              <AreaChart data={filledDaily} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" tickFormatter={(v) => v.slice(8)} />
                <YAxis />
                <Tooltip />
                <Area type="monotone" dataKey="checks" stroke="#3498db" fill="#3498db" fillOpacity={0.2} name="Total Checks" />
                <Area type="monotone" dataKey="blocks" stroke="#e74c3c" fill="#e74c3c" fillOpacity={0.4} name="Blocked" />
                <Area type="monotone" dataKey="warns" stroke="#f39c12" fill="#f39c12" fillOpacity={0.3} name="Warned" />
              </AreaChart>
            </ResponsiveContainer>
          </Box>
        </Card>
      </Grid>

      {/* Recent blocked events */}
      <Grid item xs={12}>
        <Card elevation={3}>
          <H4 sx={{ p: 2 }}>{t("projects.knowledge.guardAnalytics.recentBlocked", { count: eventsTotal })}</H4>
          <Divider />
          {events.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ p: 2 }}>
              {t("projects.knowledge.guardAnalytics.noBlocked")}
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell sx={{ pl: 2 }}>{t("projects.knowledge.guardAnalytics.date")}</TableCell>
                  <TableCell>{t("projects.knowledge.guardAnalytics.phase")}</TableCell>
                  <TableCell>{t("projects.knowledge.guardAnalytics.guard")}</TableCell>
                  <TableCell>{t("projects.knowledge.guardAnalytics.text")}</TableCell>
                  <TableCell sx={{ pr: 2 }}>{t("projects.knowledge.guardAnalytics.guardResponse")}</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {events.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell sx={{ pl: 2, whiteSpace: "nowrap" }}>
                      {e.date ? new Date(e.date).toLocaleString() : ""}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={e.phase}
                        size="small"
                        color={e.phase === "input" ? "primary" : "secondary"}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell>{e.guard_project}</TableCell>
                    <TableCell sx={{ maxWidth: 250, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {e.text_checked || t("projects.knowledge.guardAnalytics.loggingDisabled")}
                    </TableCell>
                    <TableCell sx={{ pr: 2, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {e.guard_response || ""}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Card>
      </Grid>
    </Grid>
  );
}
