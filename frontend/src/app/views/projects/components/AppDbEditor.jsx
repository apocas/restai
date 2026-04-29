import { useState, useEffect, useCallback } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Pagination,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
  styled,
} from "@mui/material";
import {
  Add,
  Delete,
  Edit,
  Refresh,
  Storage,
} from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Pane = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(1.5),
  display: "flex",
  flexDirection: "column",
  gap: theme.spacing(1),
  minHeight: 320,
}));

const PAGE_SIZE = 25;

// Format a SQLite cell value for display in a TableCell. NULL renders as
// a muted italic "NULL"; everything else as its string repr.
function CellView({ value }) {
  if (value === null || value === undefined) {
    return (
      <Typography variant="caption" color="text.disabled" sx={{ fontStyle: "italic" }}>
        NULL
      </Typography>
    );
  }
  if (typeof value === "boolean") return value ? "1" : "0";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (text.length > 80) return text.slice(0, 80) + "…";
  return text;
}

// Edit dialog — one TextField per column, NULL toggle. Used for both insert
// (rowid=null, fresh values) and update (rowid set, values pre-filled).
function RowDialog({ open, onClose, columns, initialValues, rowid, onSave, saving }) {
  const { t } = useTranslation();
  const [values, setValues] = useState(initialValues || {});

  useEffect(() => {
    setValues(initialValues || {});
  }, [initialValues, open]);

  const setField = (name, v) => setValues((prev) => ({ ...prev, [name]: v }));

  return (
    <Dialog open={open} onClose={() => !saving && onClose()} fullWidth maxWidth="sm">
      <DialogTitle>
        {rowid != null
          ? t("projects.app.db.editRow", "Edit row #{{rowid}}", { rowid })
          : t("projects.app.db.insertRow", "Insert row")}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {columns.map((col) => {
            const isNull = values[col.name] === null;
            return (
              <Box key={col.name}>
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 0.5 }}>
                  <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                    {col.name}{" "}
                    <Chip label={col.type || "TEXT"} size="small" sx={{ ml: 0.5, fontSize: 10, height: 18 }} />
                    {col.pk && <Chip label="PK" size="small" color="primary" sx={{ ml: 0.5, fontSize: 10, height: 18 }} />}
                    {col.notnull && <Chip label="NOT NULL" size="small" sx={{ ml: 0.5, fontSize: 10, height: 18 }} />}
                  </Typography>
                  {!col.notnull && (
                    <Button
                      size="small"
                      onClick={() => setField(col.name, isNull ? "" : null)}
                      disabled={saving}
                    >
                      {isNull
                        ? t("projects.app.db.setValue", "Set value")
                        : t("projects.app.db.setNull", "Set NULL")}
                    </Button>
                  )}
                </Box>
                <TextField
                  fullWidth
                  size="small"
                  value={isNull ? "" : (values[col.name] ?? "")}
                  disabled={isNull || saving}
                  onChange={(e) => setField(col.name, e.target.value)}
                  placeholder={isNull ? "NULL" : ""}
                  InputProps={{ sx: { fontFamily: "ui-monospace, Menlo, monospace", fontSize: "0.85rem" } }}
                />
              </Box>
            );
          })}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={saving}>{t("common.cancel", "Cancel")}</Button>
        <Button
          variant="contained"
          onClick={() => onSave(values)}
          disabled={saving}
          startIcon={saving ? <CircularProgress size={14} /> : null}
        >
          {t("projects.app.db.save", "Save")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

export default function AppDbEditor({ projectId, token }) {
  const { t } = useTranslation();
  const [tables, setTables] = useState([]);
  const [tablesError, setTablesError] = useState(null);
  const [loadingTables, setLoadingTables] = useState(false);

  const [activeTable, setActiveTable] = useState(null);
  const [columns, setColumns] = useState([]);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1); // 1-indexed for MUI <Pagination>
  const [loadingRows, setLoadingRows] = useState(false);

  const [editing, setEditing] = useState(null); // { rowid, values } | null
  const [saving, setSaving] = useState(false);

  const fetchTables = useCallback(() => {
    setLoadingTables(true);
    setTablesError(null);
    return api.get(`/projects/${projectId}/app/db/tables`, token)
      .then((d) => setTables(d.tables || []))
      .catch((e) => {
        if (e?.status === 404) setTablesError("noDb");
        else setTablesError(e?.message || "load failed");
      })
      .finally(() => setLoadingTables(false));
  }, [projectId, token]);

  const fetchRows = useCallback((table, p = 1) => {
    if (!table) return;
    setLoadingRows(true);
    const offset = (p - 1) * PAGE_SIZE;
    api.get(
      `/projects/${projectId}/app/db/rows?table=${encodeURIComponent(table)}&offset=${offset}&limit=${PAGE_SIZE}`,
      token
    )
      .then((d) => {
        setColumns(d.columns || []);
        setRows(d.rows || []);
        setTotal(d.total || 0);
      })
      .catch((e) => toast.error(e?.message || "rows load failed"))
      .finally(() => setLoadingRows(false));
  }, [projectId, token]);

  useEffect(() => {
    fetchTables();
  }, [fetchTables]);

  useEffect(() => {
    if (activeTable) {
      setPage(1);
      fetchRows(activeTable, 1);
    }
  }, [activeTable, fetchRows]);

  const onPageChange = (_, p) => {
    setPage(p);
    fetchRows(activeTable, p);
  };

  const startInsert = () => {
    const values = {};
    columns.forEach((c) => { values[c.name] = c.notnull ? "" : null; });
    setEditing({ rowid: null, values });
  };

  const startEdit = (row) => {
    const { rowid, ...values } = row;
    setEditing({ rowid, values });
  };

  const saveRow = async (values) => {
    if (!activeTable || !editing) return;
    setSaving(true);
    try {
      if (editing.rowid != null) {
        await api.put(`/projects/${projectId}/app/db/rows`,
          { table: activeTable, rowid: editing.rowid, values }, token);
      } else {
        await api.post(`/projects/${projectId}/app/db/rows`,
          { table: activeTable, values }, token);
      }
      toast.success(t("projects.app.db.saved", "Row saved"));
      setEditing(null);
      // Refresh list + table list (row count changed for inserts).
      fetchRows(activeTable, page);
      fetchTables();
    } catch (e) {
      toast.error(e?.message || "save failed");
    } finally {
      setSaving(false);
    }
  };

  const deleteRow = async (rowid) => {
    if (!window.confirm(t("projects.app.db.confirmDelete", "Delete this row?"))) return;
    try {
      // api.delete doesn't always pass body; use raw fetch to send JSON body.
      const url = `${process.env.REACT_APP_RESTAI_API_URL || ""}/projects/${projectId}/app/db/rows`;
      const res = await fetch(url, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Basic " + token,
        },
        body: JSON.stringify({ table: activeTable, rowid }),
      });
      if (!res.ok) {
        const txt = await res.text();
        throw new Error(`HTTP ${res.status}: ${txt}`);
      }
      toast.success(t("projects.app.db.deleted", "Row deleted"));
      fetchRows(activeTable, page);
      fetchTables();
    } catch (e) {
      toast.error(e?.message || "delete failed");
    }
  };

  if (tablesError === "noDb") {
    return (
      <Alert severity="info">
        {t(
          "projects.app.db.noDatabase",
          "No database.sqlite at the project root. Create one from the file tree (or have the AI scaffold one) to enable the DB editor."
        )}
      </Alert>
    );
  }

  return (
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: "260px 1fr",
        gap: 2,
        minHeight: "60vh",
      }}
    >
      <Pane variant="outlined">
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="subtitle2">
            {t("projects.app.db.tables", "Tables")}
          </Typography>
          <Tooltip title={t("projects.app.db.refresh", "Refresh")}>
            <IconButton size="small" onClick={fetchTables}><Refresh fontSize="small" /></IconButton>
          </Tooltip>
        </Box>
        {loadingTables ? (
          <CircularProgress size={20} />
        ) : tables.length === 0 ? (
          <Typography variant="caption" color="text.secondary">
            {t("projects.app.db.noTables", "No tables yet.")}
          </Typography>
        ) : (
          <List dense disablePadding sx={{ overflow: "auto", flexGrow: 1 }}>
            {tables.map((t_) => (
              <ListItemButton
                key={t_.name}
                dense
                selected={t_.name === activeTable}
                onClick={() => setActiveTable(t_.name)}
              >
                <Storage fontSize="small" sx={{ mr: 1, color: "action.active" }} />
                <ListItemText
                  primary={t_.name}
                  secondary={t("projects.app.db.rowCount", "{{count}} rows", { count: t_.row_count })}
                  primaryTypographyProps={{ variant: "body2", sx: { fontFamily: "monospace" } }}
                  secondaryTypographyProps={{ variant: "caption" }}
                />
              </ListItemButton>
            ))}
          </List>
        )}
      </Pane>

      <Pane variant="outlined" sx={{ overflow: "hidden" }}>
        {!activeTable ? (
          <Typography variant="caption" color="text.secondary">
            {t("projects.app.db.pickTable", "Pick a table on the left to view rows.")}
          </Typography>
        ) : (
          <>
            <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
              <Typography variant="subtitle2" sx={{ fontFamily: "monospace" }}>
                {activeTable}{" "}
                <Typography component="span" variant="caption" color="text.secondary">
                  ({total} {t("projects.app.db.rowsLower", "rows")})
                </Typography>
              </Typography>
              <Stack direction="row" spacing={1}>
                <Button
                  size="small"
                  startIcon={<Add />}
                  onClick={startInsert}
                  variant="outlined"
                >
                  {t("projects.app.db.insert", "Insert row")}
                </Button>
                <Tooltip title={t("projects.app.db.refresh", "Refresh")}>
                  <IconButton size="small" onClick={() => fetchRows(activeTable, page)}>
                    <Refresh fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Stack>
            </Box>
            <TableContainer sx={{ flexGrow: 1, overflow: "auto" }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    {columns.map((c) => (
                      <TableCell key={c.name} sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                        {c.name}{" "}
                        <Typography component="span" variant="caption" color="text.disabled">
                          {c.type}
                        </Typography>
                      </TableCell>
                    ))}
                    <TableCell align="right" sx={{ width: 90 }}>{t("projects.app.db.actions", "Actions")}</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {loadingRows ? (
                    <TableRow>
                      <TableCell colSpan={columns.length + 1} align="center">
                        <CircularProgress size={20} />
                      </TableCell>
                    </TableRow>
                  ) : rows.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={columns.length + 1} align="center">
                        <Typography variant="caption" color="text.secondary">
                          {t("projects.app.db.empty", "No rows.")}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ) : (
                    rows.map((r) => (
                      <TableRow key={r.rowid} hover>
                        {columns.map((c) => (
                          <TableCell key={c.name} sx={{ fontFamily: "monospace", fontSize: "0.8rem", maxWidth: 280 }}>
                            <CellView value={r[c.name]} />
                          </TableCell>
                        ))}
                        <TableCell align="right">
                          <Tooltip title={t("projects.app.db.edit", "Edit")}>
                            <IconButton size="small" onClick={() => startEdit(r)}><Edit fontSize="small" /></IconButton>
                          </Tooltip>
                          <Tooltip title={t("projects.app.db.delete", "Delete")}>
                            <IconButton size="small" onClick={() => deleteRow(r.rowid)}><Delete fontSize="small" /></IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
            {total > PAGE_SIZE && (
              <Box sx={{ display: "flex", justifyContent: "center", mt: 1 }}>
                <Pagination
                  count={Math.ceil(total / PAGE_SIZE)}
                  page={page}
                  onChange={onPageChange}
                  size="small"
                />
              </Box>
            )}
          </>
        )}
      </Pane>

      <RowDialog
        open={editing !== null}
        onClose={() => setEditing(null)}
        columns={columns}
        initialValues={editing?.values || {}}
        rowid={editing?.rowid ?? null}
        onSave={saveRow}
        saving={saving}
      />
    </Box>
  );
}
