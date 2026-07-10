import { useState, useEffect } from "react";
import {
  Box, Button, Chip, IconButton, Tooltip, styled, Switch,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem,
  Typography, Alert, Checkbox, FormControlLabel, CircularProgress, Divider,
} from "@mui/material";
import { Add, Edit, Delete, Image as ImageIcon, PlayArrow, CloudDownload, Search } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import DataList from "app/components/DataList";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  const auth = useAuth();
  const navigate = useNavigate();
  const isAdmin = auth.user?.is_admin;
  const [generators, setGenerators] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null); // null = create, else row
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);

  // Import-from-OpenAI-compatible-endpoint dialog state.
  const [importOpen, setImportOpen] = useState(false);
  const [importBaseUrl, setImportBaseUrl] = useState("https://api.openai.com/v1");
  const [importApiKey, setImportApiKey] = useState("");
  const [importPrefix, setImportPrefix] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discovered, setDiscovered] = useState(null); // null = not discovered yet
  const [selectedModels, setSelectedModels] = useState({});
  const [importing, setImporting] = useState(false);

  const fetchGenerators = () => {
    api.get("/image_generators", auth.user.token)
      .then((d) => setGenerators(Array.isArray(d) ? d : []))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("imageGen.title");
    fetchGenerators();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

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
        toast.success(value ? t("imageGen.dialog.enabledToast", { name: row.name }) : t("imageGen.dialog.disabledToast", { name: row.name }));
        fetchGenerators();
      })
      .catch(() => {});
  };

  const handleDelete = (e, row) => {
    e.stopPropagation();
    if (row.class_name === "local") {
      toast.warning(t("imageGen.dialog.localCannotDelete"));
      return;
    }
    if (!window.confirm(t("imageGen.dialog.deleteConfirm", { name: row.name }))) return;
    api.delete(`/image_generators/${row.id}`, auth.user.token)
      .then(() => {
        toast.success(t("imageGen.dialog.deleted", { name: row.name }));
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
          toast.success(t("imageGen.dialog.saved", { name: editing.name }));
          setDialogOpen(false);
          setEditing(null);
          fetchGenerators();
        })
        .catch(() => {})
        .finally(() => setSaving(false));
    } else {
      api.post("/image_generators", form, auth.user.token)
        .then(() => {
          toast.success(t("imageGen.dialog.created", { name: form.name }));
          setDialogOpen(false);
          fetchGenerators();
        })
        .catch(() => {})
        .finally(() => setSaving(false));
    }
  };

  const openImport = () => {
    setImportBaseUrl("https://api.openai.com/v1");
    setImportApiKey("");
    setImportPrefix("");
    setDiscovered(null);
    setSelectedModels({});
    setImportOpen(true);
  };

  const closeImport = () => {
    if (discovering || importing) return;
    setImportOpen(false);
  };

  const doDiscover = () => {
    const base = importBaseUrl.trim();
    if (!base) return;
    setDiscovering(true);
    setDiscovered(null);
    setSelectedModels({});
    api.post("/tools/openai-compat/discover", { base_url: base, api_key: importApiKey }, auth.user.token)
      .then((d) => {
        const models = Array.isArray(d?.models) ? d.models : [];
        setDiscovered(models);
        if (models.length === 0) toast.info(t("imageGen.import.noModels"));
      })
      .catch((e) => {
        setDiscovered(null);
        toast.error(e?.detail || e?.message || t("imageGen.import.discoverFailed"));
      })
      .finally(() => setDiscovering(false));
  };

  const toggleModel = (id) => setSelectedModels((s) => ({ ...s, [id]: !s[id] }));

  const anySelected = (discovered || []).some((m) => selectedModels[m.id]);
  const allSelected = discovered && discovered.length > 0 && discovered.every((m) => selectedModels[m.id]);

  const toggleAll = () => {
    if (!discovered) return;
    if (allSelected) setSelectedModels({});
    else setSelectedModels(Object.fromEntries(discovered.map((m) => [m.id, true])));
  };

  // RESTai row name must match validate_safe_name (^[a-zA-Z0-9._:-]+$); keep the
  // original id in options.model so the provider can still resolve it upstream.
  const sanitizeName = (s) => (s || "").replace(/[^a-zA-Z0-9._:-]+/g, "-").replace(/^-+|-+$/g, "") || "generator";

  const doImport = async () => {
    const chosen = (discovered || []).filter((m) => selectedModels[m.id]);
    if (chosen.length === 0) return;
    setImporting(true);
    const base = importBaseUrl.trim();
    const prefix = importPrefix.trim();
    const results = await Promise.allSettled(
      chosen.map((m) =>
        api.post("/image_generators", {
          name: sanitizeName((prefix ? prefix + "-" : "") + m.id),
          class_name: "openai",
          privacy: "public",
          description: t("imageGen.import.importedDesc", { url: base }),
          enabled: true,
          options: { model: m.id, api_key: importApiKey, base_url: base },
        }, auth.user.token)
      )
    );
    const imported = results.filter((r) => r.status === "fulfilled").length;
    const skipped = results.length - imported;
    setImporting(false);
    toast.success(t("imageGen.import.done", { imported, skipped }));
    setImportOpen(false);
    fetchGenerators();
  };

  const columns = [
    {
      key: "name",
      label: t("imageGen.columns.name"),
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
      label: t("imageGen.columns.provider"),
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
      label: t("imageGen.columns.model"),
      render: (row) => (
        <Box sx={{ fontFamily: "monospace", fontSize: "0.85rem", color: "text.secondary" }}>
          {row.options?.model || (row.class_name === "local" ? "(worker)" : "—")}
        </Box>
      ),
    },
    {
      key: "privacy",
      label: t("imageGen.columns.privacy"),
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
      label: t("imageGen.columns.enabled"),
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

  const enabledCount = generators.filter((g) => g.enabled).length;

  return (
    <Container>
      <PageHero
        icon={<ImageIcon sx={{ color: "#fff" }} />}
        eyebrow="IMAGE GENERATORS"
        title="Image Generators"
        subtitle={t("imageGen.subtitle")}
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${generators.length} configured` },
          { glyph: "★", color: "#7dd3fc", label: `${enabledCount} enabled` },
        ]}
        actions={
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              variant="outlined"
              startIcon={<PlayArrow />}
              onClick={() => navigate("/image")}
              sx={{ color: "#fff", borderColor: "rgba(255,255,255,0.4)", "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" } }}
            >
              {t("imageGen.playground")}
            </Button>
            {isAdmin && (
              <Button
                variant="outlined"
                startIcon={<CloudDownload />}
                onClick={openImport}
                sx={{ color: "#fff", borderColor: "rgba(255,255,255,0.4)", "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" } }}
              >
                {t("imageGen.import.button")}
              </Button>
            )}
            {isAdmin && (
              <Button variant="contained" startIcon={<Add />} onClick={openCreate}>
                {t("imageGen.new")}
              </Button>
            )}
          </Box>
        }
      />

      <DataList
        data={generators}
        columns={columns}
        searchKeys={["name", "class_name", "description"]}
        filters={[
          {
            key: "class_name",
            label: t("imageGen.columns.provider"),
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
        actions={(row) => (
          <>
            {isAdmin && (
              <>
                <Tooltip title={t("imageGen.actions.edit")}>
                  <IconButton size="small" onClick={() => openEdit(row)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={row.class_name === "local" ? t("imageGen.actions.deleteLocal") : t("imageGen.actions.delete")}>
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
        emptyMessage={t("imageGen.empty")}
      />

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editing ? t("imageGen.dialog.editTitle", { name: editing.name }) : t("imageGen.dialog.newTitle")}
        </DialogTitle>
        <DialogContent>
          {editing?.class_name === "local" && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {t("imageGen.dialog.localInfo", { name: editing.name })}
            </Alert>
          )}

          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label={t("imageGen.dialog.name")}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              disabled={!!editing}
              required
              helperText={editing ? "" : t("imageGen.dialog.nameHelp")}
              fullWidth
            />

            {(!editing || editing.class_name !== "local") && (
              <TextField
                select
                label={t("imageGen.dialog.provider")}
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
              label={t("imageGen.dialog.privacy")}
              value={form.privacy}
              onChange={(e) => setForm((f) => ({ ...f, privacy: e.target.value }))}
              fullWidth
            >
              <MenuItem value="public">{t("imageGen.dialog.privacyPublic")}</MenuItem>
              <MenuItem value="private">{t("imageGen.dialog.privacyPrivate")}</MenuItem>
            </TextField>

            <TextField
              label={t("imageGen.dialog.description")}
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
              <Typography variant="body2">{t("imageGen.dialog.enabled")}</Typography>
            </Box>

            {(!editing || editing.class_name !== "local") && (
              <>
                <Typography variant="subtitle2" sx={{ mt: 1 }}>{t("imageGen.dialog.providerOptions")}</Typography>
                <TextField
                  label={t("imageGen.dialog.model")}
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
                  label={t("imageGen.dialog.apiKey")}
                  type="password"
                  value={form.options?.api_key ?? ""}
                  onChange={(e) => setOption("api_key", e.target.value)}
                  required={!editing}
                  fullWidth
                  helperText={editing ? t("imageGen.dialog.apiKeyHelp") : ""}
                />
                {form.class_name === "openai" && (
                  <TextField
                    label={t("imageGen.dialog.baseUrl")}
                    value={form.options?.base_url ?? ""}
                    onChange={(e) => setOption("base_url", e.target.value)}
                    fullWidth
                    placeholder="https://api.openai.com/v1"
                    helperText={t("imageGen.dialog.baseUrlHelp")}
                  />
                )}
              </>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={saving}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? t("imageGen.dialog.saving") : (editing ? t("imageGen.dialog.save") : t("imageGen.dialog.create"))}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={importOpen} onClose={closeImport} maxWidth="sm" fullWidth>
        <DialogTitle>{t("imageGen.import.title")}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t("imageGen.import.intro")}
            </Typography>

            <TextField
              label={t("imageGen.import.baseUrl")}
              value={importBaseUrl}
              onChange={(e) => setImportBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              helperText={t("imageGen.import.baseUrlHelp")}
              fullWidth
              disabled={discovering || importing}
            />
            <TextField
              label={t("imageGen.import.apiKey")}
              type="password"
              value={importApiKey}
              onChange={(e) => setImportApiKey(e.target.value)}
              fullWidth
              disabled={discovering || importing}
            />
            <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
              <Button
                variant="outlined"
                onClick={doDiscover}
                disabled={!importBaseUrl.trim() || discovering || importing}
                startIcon={discovering ? <CircularProgress size={16} /> : <Search />}
              >
                {discovering ? t("imageGen.import.discovering") : t("imageGen.import.discover")}
              </Button>
            </Box>

            {discovered && discovered.length > 0 && (
              <>
                <Divider />
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <Typography variant="subtitle2">
                    {t("imageGen.import.modelsFound", { count: discovered.length })}
                  </Typography>
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        checked={!!allSelected}
                        indeterminate={!allSelected && anySelected}
                        onChange={toggleAll}
                      />
                    }
                    label={t("imageGen.import.selectAll")}
                  />
                </Box>
                <TextField
                  label={t("imageGen.import.prefix")}
                  value={importPrefix}
                  onChange={(e) => setImportPrefix(e.target.value)}
                  helperText={t("imageGen.import.prefixHelp")}
                  size="small"
                  fullWidth
                  disabled={importing}
                />
                <Box sx={{ maxHeight: 260, overflowY: "auto", border: 1, borderColor: "divider", borderRadius: 1, px: 1 }}>
                  {discovered.map((m) => (
                    <Box key={m.id} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Checkbox
                        size="small"
                        checked={!!selectedModels[m.id]}
                        onChange={() => toggleModel(m.id)}
                        disabled={importing}
                      />
                      <Box sx={{ minWidth: 0 }}>
                        <Typography sx={{ fontFamily: "monospace", fontSize: "0.85rem" }} noWrap>{m.id}</Typography>
                        {m.owned_by && (
                          <Typography variant="caption" color="text.secondary" noWrap>{m.owned_by}</Typography>
                        )}
                      </Box>
                    </Box>
                  ))}
                </Box>
              </>
            )}

            {discovered && discovered.length === 0 && (
              <Alert severity="info">{t("imageGen.import.noModels")}</Alert>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeImport} disabled={discovering || importing}>{t("common.cancel")}</Button>
          <Button
            variant="contained"
            onClick={doImport}
            disabled={importing || !anySelected}
          >
            {importing
              ? t("imageGen.import.importing")
              : t("imageGen.import.importSelected", { count: (discovered || []).filter((m) => selectedModels[m.id]).length })}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
