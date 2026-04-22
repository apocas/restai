import { useState, useEffect } from "react";
import {
  Box, Button, Chip, IconButton, Tooltip, styled, Switch,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem,
  Typography, Alert,
} from "@mui/material";
import { Add, Edit, Delete, Image as ImageIcon, PlayArrow } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import DataList from "app/components/DataList";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

const PROVIDERS = [
  { value: "openai", label: "OpenAI / OpenAI-compatible" },
  { value: "google", label: "Google (Imagen / Nano Banana)" },
];

const PROVIDER_DEFAULT_OPTIONS = {
  openai: { model: "gpt-image-1.5", api_key: "", base_url: "" },
  google: { model: "imagen-3.0-generate-001", api_key: "" },
};

function emptyForm() {
  return {
    name: "",
    class_name: "openai",
    privacy: "public",
    description: "",
    enabled: true,
    options: { ...PROVIDER_DEFAULT_OPTIONS.openai },
  };
}

export default function ImageGenerators() {
  const auth = useAuth();
  const navigate = useNavigate();
  const isAdmin = auth.user?.is_admin;
  const [generators, setGenerators] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null); // null = create, else row
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);

  const fetchGenerators = () => {
    api.get("/image_generators", auth.user.token)
      .then((d) => setGenerators(Array.isArray(d) ? d : []))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Image Generators";
    fetchGenerators();
  }, []);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setDialogOpen(true);
  };

  const openEdit = (row) => {
    setEditing(row);
    setForm({
      name: row.name,
      class_name: row.class_name,
      privacy: row.privacy || "public",
      description: row.description || "",
      enabled: !!row.enabled,
      options: row.options || {},
    });
    setDialogOpen(true);
  };

  const closeDialog = () => {
    if (saving) return;
    setDialogOpen(false);
    setEditing(null);
  };

  const handleClassChange = (newClass) => {
    setForm((f) => ({
      ...f,
      class_name: newClass,
      options: { ...PROVIDER_DEFAULT_OPTIONS[newClass], ...(f.options || {}) },
    }));
  };

  const setOption = (key, value) => {
    setForm((f) => ({ ...f, options: { ...f.options, [key]: value } }));
  };

  const handleToggleEnabled = (row, value) => {
    api.patch(`/image_generators/${row.id}`, { enabled: value }, auth.user.token)
      .then(() => {
        toast.success(`${row.name} ${value ? "enabled" : "disabled"}`);
        fetchGenerators();
      })
      .catch(() => {});
  };

  const handleDelete = (e, row) => {
    e.stopPropagation();
    if (row.class_name === "local") {
      toast.warning("Local generators cannot be deleted. Disable instead.");
      return;
    }
    if (!window.confirm(`Delete image generator "${row.name}"?`)) return;
    api.delete(`/image_generators/${row.id}`, auth.user.token)
      .then(() => {
        toast.success(`Deleted ${row.name}`);
        fetchGenerators();
      })
      .catch(() => {});
  };

  const handleSave = () => {
    setSaving(true);
    if (editing) {
      // PATCH — for local, only send fields that are settable.
      const payload = {
        privacy: form.privacy,
        description: form.description,
        enabled: form.enabled,
      };
      if (editing.class_name !== "local") {
        payload.class_name = form.class_name;
        payload.options = form.options;
      }
      api.patch(`/image_generators/${editing.id}`, payload, auth.user.token)
        .then(() => {
          toast.success(`Saved ${editing.name}`);
          setDialogOpen(false);
          setEditing(null);
          fetchGenerators();
        })
        .catch(() => {})
        .finally(() => setSaving(false));
    } else {
      api.post("/image_generators", form, auth.user.token)
        .then(() => {
          toast.success(`Created ${form.name}`);
          setDialogOpen(false);
          fetchGenerators();
        })
        .catch(() => {})
        .finally(() => setSaving(false));
    }
  };

  const columns = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 32, height: 32, borderRadius: "8px",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "rgba(139,92,246,0.12)",
            }}
          >
            <ImageIcon sx={{ fontSize: 18, color: "#8b5cf6" }} />
          </Box>
          <Box sx={{ fontWeight: 500 }}>{row.name}</Box>
        </Box>
      ),
    },
    {
      key: "class_name",
      label: "Provider",
      sortable: true,
      render: (row) => (
        <Chip
          size="small"
          label={row.class_name}
          sx={{ fontFamily: "monospace", fontSize: "0.72rem" }}
        />
      ),
    },
    {
      key: "model",
      label: "Model",
      render: (row) => (
        <Box sx={{ fontFamily: "monospace", fontSize: "0.85rem", color: "text.secondary" }}>
          {row.options?.model || (row.class_name === "local" ? "(worker)" : "—")}
        </Box>
      ),
    },
    {
      key: "privacy",
      label: "Privacy",
      sortable: true,
      render: (row) => (
        <Chip
          label={row.privacy}
          size="small"
          sx={{
            backgroundColor: row.privacy === "private" ? "rgba(239,68,68,0.12)" : "rgba(16,185,129,0.12)",
            color: row.privacy === "private" ? "#ef4444" : "#10b981",
            fontWeight: 600, fontSize: "0.72rem", textTransform: "uppercase", height: 22,
          }}
        />
      ),
    },
    {
      key: "enabled",
      label: "Enabled",
      sortable: true,
      align: "center",
      render: (row) => (
        <Switch
          size="small"
          checked={!!row.enabled}
          disabled={!isAdmin}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => handleToggleEnabled(row, e.target.checked)}
        />
      ),
    },
  ];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Image Generators", path: "/image_generators" }]} />
      </Box>

      <DataList
        title="Image Generators"
        subtitle="Local workers + external providers (OpenAI, Google) — admins manage credentials per row"
        data={generators}
        columns={columns}
        searchKeys={["name", "class_name", "description"]}
        filters={[
          {
            key: "class_name",
            label: "Provider",
            options: [
              { value: "local", label: "Local" },
              { value: "openai", label: "OpenAI" },
              { value: "google", label: "Google" },
            ],
          },
        ]}
        onRowClick={(row) => isAdmin && openEdit(row)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              variant="outlined"
              startIcon={<PlayArrow />}
              onClick={() => navigate("/image")}
            >
              Playground
            </Button>
            {isAdmin && (
              <Button variant="contained" startIcon={<Add />} onClick={openCreate}>
                New Generator
              </Button>
            )}
          </Box>
        }
        actions={(row) => (
          <>
            {isAdmin && (
              <>
                <Tooltip title="Edit">
                  <IconButton size="small" onClick={() => openEdit(row)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={row.class_name === "local" ? "Local generators cannot be deleted" : "Delete"}>
                  <span>
                    <IconButton
                      size="small"
                      color="error"
                      disabled={row.class_name === "local"}
                      onClick={(e) => handleDelete(e, row)}
                    >
                      <Delete fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              </>
            )}
          </>
        )}
        emptyMessage="No image generators configured."
      />

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editing ? `Edit ${editing.name}` : "New Image Generator"}
        </DialogTitle>
        <DialogContent>
          {editing?.class_name === "local" && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Local generator from <code>restai/image/workers/{editing.name}.py</code>. You can toggle <em>enabled</em>, set privacy + description, and assign to teams. Provider + options come from the worker module.
            </Alert>
          )}

          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label="Name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              disabled={!!editing}
              required
              helperText={editing ? "" : "URL-safe identifier — letters, numbers, dots, hyphens, underscores"}
              fullWidth
            />

            {(!editing || editing.class_name !== "local") && (
              <TextField
                select
                label="Provider"
                value={form.class_name}
                onChange={(e) => handleClassChange(e.target.value)}
                disabled={!!editing}
                fullWidth
              >
                {PROVIDERS.map((p) => (
                  <MenuItem key={p.value} value={p.value}>{p.label}</MenuItem>
                ))}
              </TextField>
            )}

            <TextField
              select
              label="Privacy"
              value={form.privacy}
              onChange={(e) => setForm((f) => ({ ...f, privacy: e.target.value }))}
              fullWidth
            >
              <MenuItem value="public">Public (cloud-hosted)</MenuItem>
              <MenuItem value="private">Private (self-hosted / local)</MenuItem>
            </TextField>

            <TextField
              label="Description"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              fullWidth
              multiline
              rows={2}
            />

            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Switch
                checked={form.enabled}
                onChange={(e) => setForm((f) => ({ ...f, enabled: e.target.checked }))}
              />
              <Typography variant="body2">Enabled</Typography>
            </Box>

            {(!editing || editing.class_name !== "local") && (
              <>
                <Typography variant="subtitle2" sx={{ mt: 1 }}>Provider Options</Typography>
                <TextField
                  label="Model"
                  value={form.options?.model ?? ""}
                  onChange={(e) => setOption("model", e.target.value)}
                  required
                  fullWidth
                  helperText={
                    form.class_name === "openai"
                      ? "e.g. gpt-image-1.5, dall-e-3"
                      : "e.g. imagen-3.0-generate-001, nano-banana"
                  }
                />
                <TextField
                  label="API Key"
                  type="password"
                  value={form.options?.api_key ?? ""}
                  onChange={(e) => setOption("api_key", e.target.value)}
                  required={!editing}
                  fullWidth
                  helperText={editing ? "Leave as ******** to keep the existing key" : ""}
                />
                {form.class_name === "openai" && (
                  <TextField
                    label="Base URL (optional, for OpenAI-compatible providers)"
                    value={form.options?.base_url ?? ""}
                    onChange={(e) => setOption("base_url", e.target.value)}
                    fullWidth
                    placeholder="https://api.openai.com/v1"
                    helperText="Leave empty for OpenAI proper. Set for Together / Groq / vLLM / self-hosted."
                  />
                )}
              </>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={saving}>Cancel</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : (editing ? "Save" : "Create")}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
