import { useState, useEffect } from "react";
import {
  Box, Card, Chip, Divider, Grid, styled, Typography,
  Table, TableBody, TableCell, TableHead, TableRow,
  TextField, MenuItem, Button, IconButton,
} from "@mui/material";
import { History, ChevronLeft, ChevronRight, FileDownload } from "@mui/icons-material";
import Breadcrumb from "app/components/Breadcrumb";
import { H4 } from "app/components/Typography";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toCsv, downloadCsv } from "app/utils/csvExport";

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

const ACTION_COLORS = {
  POST: "success",
  PATCH: "info",
  PUT: "info",
  DELETE: "error",
};

export default function AuditLog() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [filterUsername, setFilterUsername] = useState("");
  const [filterAction, setFilterAction] = useState("");
  const pageSize = 25;

  const fetchEntries = () => {
    const params = new URLSearchParams({
      start: page * pageSize,
      end: (page + 1) * pageSize,
    });
    if (filterUsername) params.set("username", filterUsername);
    if (filterAction) params.set("action", filterAction);

    api.get("/audit?" + params.toString(), auth.user.token, { silent: true })
      .then((data) => {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      })
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("audit.title");
    fetchEntries();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, filterUsername, filterAction, t]);

  const totalPages = Math.ceil(total / pageSize);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("audit.title"), path: "/audit" }]} />
      </Box>

      <ContentBox>
        <Card elevation={3}>
          <FlexBox justifyContent="space-between" sx={{ pr: 2 }}>
            <FlexBox>
              <History sx={{ ml: 2 }} />
              <H4 sx={{ p: 2 }}>{t("audit.title")}</H4>
              <Typography variant="caption" color="text.secondary">
                {t("audit.entries", { count: total })}
              </Typography>
            </FlexBox>
            <FlexBox sx={{ gap: 1 }}>
              <TextField
                size="small"
                label={t("audit.filterUser")}
                value={filterUsername}
                onChange={(e) => { setFilterUsername(e.target.value); setPage(0); }}
                sx={{ width: 150 }}
              />
              <TextField
                select
                size="small"
                label={t("audit.filterAction")}
                value={filterAction}
                onChange={(e) => { setFilterAction(e.target.value); setPage(0); }}
                sx={{ width: 120 }}
              >
                <MenuItem value="">{t("audit.filterAll")}</MenuItem>
                <MenuItem value="POST">POST</MenuItem>
                <MenuItem value="PATCH">PATCH</MenuItem>
                <MenuItem value="DELETE">DELETE</MenuItem>
              </TextField>
              <Button
                size="small"
                variant="outlined"
                startIcon={<FileDownload />}
                disabled={entries.length === 0}
                onClick={() => {
                  // Exports the *current page* of entries. The server
                  // paginates and full-range export would need a new
                  // endpoint; admins can bump the page size first if
                  // they need more rows in one download.
                  const csv = toCsv(entries, [
                    { key: "date", header: t("audit.columns.date") },
                    { key: "username", header: t("audit.columns.user") },
                    { key: "action", header: t("audit.columns.action") },
                    { key: "resource", header: t("audit.columns.resource") },
                    { key: "status_code", header: t("audit.columns.status") },
                  ]);
                  const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
                  downloadCsv(`audit-log-${stamp}.csv`, csv);
                }}
              >
                {t("audit.exportCsv")}
              </Button>
            </FlexBox>
          </FlexBox>
          <Divider />

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ pl: 2 }}>{t("audit.columns.date")}</TableCell>
                <TableCell>{t("audit.columns.user")}</TableCell>
                <TableCell>{t("audit.columns.action")}</TableCell>
                <TableCell>{t("audit.columns.resource")}</TableCell>
                <TableCell align="center" sx={{ pr: 2 }}>{t("audit.columns.status")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 4 }}>
                    <Typography variant="body2" color="text.secondary">{t("audit.noEntries")}</Typography>
                  </TableCell>
                </TableRow>
              ) : (
                entries.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell sx={{ pl: 2, whiteSpace: "nowrap" }}>
                      {e.date ? new Date(e.date).toLocaleString() : ""}
                    </TableCell>
                    <TableCell>{e.username || "—"}</TableCell>
                    <TableCell>
                      <Chip
                        label={e.action}
                        size="small"
                        color={ACTION_COLORS[e.action] || "default"}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell sx={{ maxWidth: 350, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      <code>{e.resource}</code>
                    </TableCell>
                    <TableCell align="center" sx={{ pr: 2 }}>
                      <Chip
                        label={e.status_code}
                        size="small"
                        color={e.status_code < 400 ? "success" : "error"}
                        variant="outlined"
                      />
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          {totalPages > 1 && (
            <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", p: 2, gap: 1 }}>
              <IconButton onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0} size="small">
                <ChevronLeft />
              </IconButton>
              <Typography variant="body2">
                {t("audit.page", { page: page + 1, total: totalPages })}
              </Typography>
              <IconButton onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1} size="small">
                <ChevronRight />
              </IconButton>
            </Box>
          )}
        </Card>
      </ContentBox>
    </Container>
  );
}
