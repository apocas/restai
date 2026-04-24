import { useEffect, useState } from "react";
import {
  Alert, Box, Button, Chip, Dialog, DialogActions, DialogContent,
  DialogTitle, IconButton, List, ListItem, ListItemText, TextField,
  Tooltip, Typography,
} from "@mui/material";
import { Add, Delete, Edit, VpnKey } from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";


function emptyForm() {
  return { name: "", value: "", description: "" };
}


export default function ProjectEditSecrets({ project }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [secrets, setSecrets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);

  const fetchSecrets = () => {
    setLoading(true);
    api.get(`/projects/${project.id}/secrets`, auth.user.token)
      .then((d) => setSecrets(Array.isArray(d) ? d : []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (project?.id) fetchSecrets();
  }, [project?.id]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setDialogOpen(true);
  };

  const openEdit = (row) => {
    setEditing(row);
    // Value is "********" on read — leave it as a sentinel the user can
    // type over. If they don't change it, we omit from the PATCH body.
    setForm({ name: row.name, value: "********", description: row.description || "" });
    setDialogOpen(true);
  };

  const closeDialog = () => {
    if (saving) return;
    setDialogOpen(false);
    setEditing(null);
  };

  const handleDelete = (row) => {
    if (!window.confirm(`Delete secret "${row.name}"? Tools relying on it will start failing.`)) return;
    api.delete(`/projects/${project.id}/secrets/${row.id}`, auth.user.token)
      .then(() => {
        toast.success(`Deleted ${row.name}`);
        fetchSecrets();
      })
      .catch(() => {});
  };

  const handleSave = () => {
    setSaving(true);
    if (editing) {
      const payload = { description: form.description };
      // Only include value if the user actually changed it — otherwise
      // the server preserves the existing stored plaintext.
      if (form.value && form.value !== "********") {
        payload.value = form.value;
      }
      api.patch(`/projects/${project.id}/secrets/${editing.id}`, payload, auth.user.token)
        .then(() => {
          toast.success(`Saved ${editing.name}`);
          setDialogOpen(false);
          setEditing(null);
          fetchSecrets();
        })
        .catch(() => {})
        .finally(() => setSaving(false));
    } else {
      if (!form.name || !form.value) {
        toast.error("Name and value are required");
        setSaving(false);
        return;
      }
      api.post(`/projects/${project.id}/secrets`, form, auth.user.token)
        .then(() => {
          toast.success(`Created ${form.name}`);
          setDialogOpen(false);
          fetchSecrets();
        })
        .catch(() => {})
        .finally(() => setSaving(false));
    }
  };

  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 2 }}>
        <Box>
          <Typography variant="h6" fontWeight={600}>{t("projects.edit.secrets.title")}</Typography>
          <Typography variant="body2" color="text.secondary">
            Credentials and tokens used by agentic tools (e.g. <code>browser_fill(secret_ref=...)</code>).
            Values are encrypted at rest and never leave the server — they are typed into the
            browser directly without entering the agent's context.
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Add />} onClick={openCreate}>{t("projects.edit.secrets.add")}</Button>
      </Box>

      {loading ? (
        <Typography variant="body2" color="text.secondary">{t("common.loading")}</Typography>
      ) : secrets.length === 0 ? (
        <Alert severity="info">No secrets configured. Add one to use credentials inside agent tools.</Alert>
      ) : (
        <List>
          {secrets.map((s) => (
            <ListItem
              key={s.id}
              sx={{ borderBottom: "1px solid", borderColor: "divider" }}
              secondaryAction={
                <Box sx={{ display: "flex", gap: 0.5 }}>
                  <Tooltip title={t("common.edit")}>
                    <IconButton size="small" onClick={() => openEdit(s)}>
                      <Edit fontSize="small" />
                    </IconButton>
                  </Tooltip>
                  <Tooltip title={t("common.delete")}>
                    <IconButton size="small" color="error" onClick={() => handleDelete(s)}>
                      <Delete fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              }
            >
              <VpnKey sx={{ mr: 1.5, color: "warning.main", fontSize: 18 }} />
              <ListItemText
                primary={
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                    <Typography component="span" sx={{ fontFamily: "monospace", fontWeight: 500 }}>
                      {s.name}
                    </Typography>
                    <Chip label="********" size="small" sx={{ fontFamily: "monospace", fontSize: "0.7rem", height: 20 }} />
                  </Box>
                }
                secondary={s.description || "(no description)"}
              />
            </ListItem>
          ))}
        </List>
      )}

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{editing ? `${t("common.edit")} ${editing.name}` : t("projects.edit.secrets.add")}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label={t("projects.edit.secrets.name")}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              disabled={!!editing}
              required
              helperText={editing ? "" : "Used as the secret_ref in tool calls — e.g. 'portal_password'"}
              fullWidth
            />
            <TextField
              label={t("projects.edit.secrets.value")}
              type="password"
              value={form.value}
              onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
              required={!editing}
              helperText={editing ? "Leave as ******** to keep the existing value." : "Encrypted at rest."}
              fullWidth
            />
            <TextField
              label={t("common.description")}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              fullWidth
              multiline
              rows={2}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={saving}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : (editing ? "Save" : "Create")}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
