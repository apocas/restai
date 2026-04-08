import { useState, useEffect, useCallback } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, IconButton, MenuItem, Paper, Table, TableBody,
  TableCell, TableContainer, TableHead, TablePagination, TableRow, TextField,
  Tooltip, Typography,
} from "@mui/material";
import { Delete, Edit, MergeType, Refresh, Search, FindReplace } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toast } from "react-toastify";

const TYPE_COLORS = {
  PERSON: "#42a5f5",
  ORG: "#66bb6a",
  LOC: "#ffa726",
  MISC: "#9e9e9e",
  DATE: "#ab47bc",
};

export default function EntitiesPanel({ project }) {
  const auth = useAuth();
  const [entities, setEntities] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(50);

  const [editing, setEditing] = useState(null);
  const [merging, setMerging] = useState(null);
  const [duplicates, setDuplicates] = useState(null);
  const [rebuilding, setRebuilding] = useState(false);

  const fetchEntities = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams();
    if (typeFilter) params.set("type", typeFilter);
    if (search) params.set("search", search);
    params.set("limit", rowsPerPage);
    params.set("offset", page * rowsPerPage);
    api.get(`/projects/${project.id}/kg/entities?${params}`, auth.user.token)
      .then((d) => { setEntities(d.entities || []); setTotal(d.total || 0); })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project.id, search, typeFilter, page, rowsPerPage]);

  useEffect(() => { fetchEntities(); }, [fetchEntities]);

  const handleDelete = (entity) => {
    if (!window.confirm(`Delete entity "${entity.name}"? This removes all its mentions and relationships.`)) return;
    api.delete(`/projects/${project.id}/kg/entities/${entity.id}`, auth.user.token)
      .then(() => { fetchEntities(); toast.success("Entity deleted"); })
      .catch(() => {});
  };

  const handleSaveEdit = () => {
    if (!editing?.name?.trim()) return;
    api.patch(`/projects/${project.id}/kg/entities/${editing.id}`, { name: editing.name }, auth.user.token)
      .then(() => { setEditing(null); fetchEntities(); toast.success("Entity renamed"); })
      .catch(() => {});
  };

  const handleMergeSubmit = () => {
    if (!merging?.target_id) return;
    api.post(`/projects/${project.id}/kg/entities/${merging.source.id}/merge`,
      { target_id: parseInt(merging.target_id) }, auth.user.token)
      .then(() => { setMerging(null); fetchEntities(); toast.success("Entities merged"); })
      .catch(() => {});
  };

  const handleFindDuplicates = () => {
    api.get(`/projects/${project.id}/kg/duplicates`, auth.user.token)
      .then((d) => setDuplicates(d.candidates || []))
      .catch(() => {});
  };

  const handleMergeDuplicate = (a, b) => {
    api.post(`/projects/${project.id}/kg/entities/${b.entity_b_id}/merge`,
      { target_id: a.entity_a_id }, auth.user.token)
      .then(() => {
        setDuplicates((prev) => prev.filter((c) => c.entity_b_id !== b.entity_b_id));
        fetchEntities();
        toast.success("Merged");
      })
      .catch(() => {});
  };

  const handleRebuild = () => {
    if (!window.confirm("Rebuild the knowledge graph from all sources? This wipes existing entities and re-extracts from scratch.")) return;
    setRebuilding(true);
    api.post(`/projects/${project.id}/kg/rebuild`, {}, auth.user.token)
      .then((d) => { toast.success(d.message || "Rebuild scheduled"); setTimeout(fetchEntities, 3000); })
      .catch(() => {})
      .finally(() => setRebuilding(false));
  };

  return (
    <Box>
      <Box sx={{ display: "flex", gap: 2, mb: 2, flexWrap: "wrap", alignItems: "center" }}>
        <TextField
          size="small"
          placeholder="Search entities..."
          value={search}
          onChange={(e) => { setSearch(e.target.value); setPage(0); }}
          InputProps={{ startAdornment: <Search fontSize="small" sx={{ mr: 1, color: "text.disabled" }} /> }}
          sx={{ minWidth: 240 }}
        />
        <TextField
          size="small" select label="Type" value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(0); }}
          sx={{ minWidth: 150 }}
        >
          <MenuItem value="">All types</MenuItem>
          <MenuItem value="PERSON">Person</MenuItem>
          <MenuItem value="ORG">Organization</MenuItem>
          <MenuItem value="LOC">Location</MenuItem>
          <MenuItem value="MISC">Other</MenuItem>
        </TextField>
        <Box sx={{ flex: 1 }} />
        <Button variant="outlined" size="small" startIcon={<FindReplace />} onClick={handleFindDuplicates}>
          Find Duplicates
        </Button>
        <Button variant="outlined" size="small" startIcon={<Refresh />} onClick={handleRebuild} disabled={rebuilding}>
          Rebuild Graph
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ textAlign: "center", py: 6 }}><CircularProgress /></Box>
      ) : entities.length === 0 ? (
        <Alert severity="info">No entities yet. Ingest documents (or click Rebuild Graph) to populate the knowledge graph.</Alert>
      ) : (
        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Name</TableCell>
                <TableCell>Type</TableCell>
                <TableCell align="right">Mentions</TableCell>
                <TableCell align="right" sx={{ width: 160 }}>Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entities.map((e) => (
                <TableRow key={e.id} hover>
                  <TableCell sx={{ fontWeight: 500 }}>{e.name}</TableCell>
                  <TableCell>
                    <Chip label={e.entity_type} size="small" sx={{
                      bgcolor: (TYPE_COLORS[e.entity_type] || "#999") + "20",
                      color: TYPE_COLORS[e.entity_type] || "#999",
                      fontWeight: 600,
                    }} />
                  </TableCell>
                  <TableCell align="right">{e.mention_count}</TableCell>
                  <TableCell align="right">
                    <Tooltip title="Rename"><IconButton size="small" onClick={() => setEditing({ ...e })}><Edit fontSize="small" /></IconButton></Tooltip>
                    <Tooltip title="Merge into another"><IconButton size="small" onClick={() => setMerging({ source: e, target_id: "" })}><MergeType fontSize="small" /></IconButton></Tooltip>
                    <Tooltip title="Delete"><IconButton size="small" color="error" onClick={() => handleDelete(e)}><Delete fontSize="small" /></IconButton></Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={total}
            page={page}
            rowsPerPage={rowsPerPage}
            onPageChange={(_, p) => setPage(p)}
            onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value)); setPage(0); }}
            rowsPerPageOptions={[25, 50, 100]}
          />
        </TableContainer>
      )}

      {/* Edit dialog */}
      {editing && (
        <Dialog open onClose={() => setEditing(null)} maxWidth="xs" fullWidth>
          <DialogTitle>Rename entity</DialogTitle>
          <DialogContent>
            <TextField
              autoFocus fullWidth size="small" label="Name" sx={{ mt: 1 }}
              value={editing.name}
              onChange={(e) => setEditing({ ...editing, name: e.target.value })}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditing(null)}>Cancel</Button>
            <Button variant="contained" onClick={handleSaveEdit}>Save</Button>
          </DialogActions>
        </Dialog>
      )}

      {/* Merge dialog */}
      {merging && (
        <Dialog open onClose={() => setMerging(null)} maxWidth="xs" fullWidth>
          <DialogTitle>Merge "{merging.source.name}" into…</DialogTitle>
          <DialogContent>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: "block" }}>
              All mentions and relationships will be moved. The source entity will be deleted.
            </Typography>
            <TextField
              fullWidth size="small" label="Target entity ID" sx={{ mt: 1 }}
              type="number"
              value={merging.target_id}
              onChange={(e) => setMerging({ ...merging, target_id: e.target.value })}
              helperText="Enter the ID of the entity to merge INTO"
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setMerging(null)}>Cancel</Button>
            <Button variant="contained" onClick={handleMergeSubmit}>Merge</Button>
          </DialogActions>
        </Dialog>
      )}

      {/* Duplicates dialog */}
      {duplicates !== null && (
        <Dialog open onClose={() => setDuplicates(null)} maxWidth="md" fullWidth>
          <DialogTitle>Potential Duplicates</DialogTitle>
          <DialogContent>
            {duplicates.length === 0 ? (
              <Alert severity="success">No potential duplicates found.</Alert>
            ) : (
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Keep</TableCell>
                    <TableCell>Merge</TableCell>
                    <TableCell align="right">Similarity</TableCell>
                    <TableCell align="right">Action</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {duplicates.map((d) => (
                    <TableRow key={`${d.entity_a_id}-${d.entity_b_id}`}>
                      <TableCell>{d.entity_a_name}</TableCell>
                      <TableCell>{d.entity_b_name}</TableCell>
                      <TableCell align="right">{(d.similarity * 100).toFixed(0)}%</TableCell>
                      <TableCell align="right">
                        <Button size="small" startIcon={<MergeType />} onClick={() => handleMergeDuplicate(d, d)}>
                          Merge
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setDuplicates(null)}>Close</Button>
          </DialogActions>
        </Dialog>
      )}
    </Box>
  );
}
