import { useState, useEffect } from "react";
import {
  Box, Button, Chip, IconButton, Tooltip, styled, Switch,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem,
  Typography, Alert, CircularProgress, Divider, FormControlLabel, Checkbox,
} from "@mui/material";
import { Add, Edit, Delete, RecordVoiceOver, PlayArrow, CloudDownload, Search } from "@mui/icons-material";
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
  { value: "openai", label: "OpenAI Whisper / OpenAI-compatible" },
  { value: "google", label: "Google Cloud Speech-to-Text" },
  { value: "deepgram", label: "Deepgram" },
  { value: "assemblyai", label: "AssemblyAI" },
];

const PROVIDER_DEFAULT_OPTIONS = {
  openai: { model: "whisper-1", api_key: "", base_url: "" },
  google: { api_key: "", language_code: "en-US", model: "" },
  deepgram: { api_key: "", model: "nova-2", language: "en" },
  assemblyai: { api_key: "", speech_model: "best" },
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

export default function SpeechToText() {
  const { t } = useTranslation();
  const auth = useAuth();
  const navigate = useNavigate();
  const isAdmin = auth.user?.is_admin;
  const [models, setModels] = useState([]);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
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

  const fetchModels = () => {
    api.get("/speech_to_text", auth.user.token)
      .then((d) => setModels(Array.isArray(d) ? d : []))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("speechGen.title");
    fetchModels();
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
    api.patch(`/speech_to_text/${row.id}`, { enabled: value }, auth.user.token)
      .then(() => {
        toast.success(value ? t("speechGen.dialog.enabledToast", { name: row.name }) : t("speechGen.dialog.disabledToast", { name: row.name }));
        fetchModels();
      })
      .catch(() => {});
  };

  const handleDelete = (e, row) => {
    e.stopPropagation();
    if (row.class_name === "local") {
      toast.warning(t("speechGen.dialog.localCannotDelete"));
      return;
    }
    if (!window.confirm(t("speechGen.dialog.deleteConfirm", { name: row.name }))) return;
    api.delete(`/speech_to_text/${row.id}`, auth.user.token)
      .then(() => {
        toast.success(t("speechGen.dialog.deleted", { name: row.name }));
        fetchModels();
      })
      .catch(() => {});
  };

  const handleSave = () => {
    setSaving(true);
    if (editing) {
      const payload = {
        privacy: form.privacy,
        description: form.description,
        enabled: form.enabled,
      };
      if (editing.class_name !== "local") {
        payload.class_name = form.class_name;
        payload.options = form.options;
      }
      api.patch(`/speech_to_text/${editing.id}`, payload, auth.user.token)
        .then(() => {
          toast.success(t("speechGen.dialog.saved", { name: editing.name }));
          setDialogOpen(false);
          setEditing(null);
          fetchModels();
        })
        .catch(() => {})
        .finally(() => setSaving(false));
    } else {
      api.post("/speech_to_text", form, auth.user.token)
        .then(() => {
          toast.success(t("speechGen.dialog.created", { name: form.name }));
          setDialogOpen(false);
          fetchModels();
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
        const list = Array.isArray(d?.models) ? d.models : [];
        setDiscovered(list);
        if (list.length === 0) toast.info(t("speechGen.import.noModels"));
      })
      .catch((e) => {
        setDiscovered(null);
        toast.error(e?.detail || e?.message || t("speechGen.import.discoverFailed"));
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
  const sanitizeName = (s) => (s || "").replace(/[^a-zA-Z0-9._:-]+/g, "-").replace(/^-+|-+$/g, "") || "engine";

  const doImport = async () => {
    const chosen = (discovered || []).filter((m) => selectedModels[m.id]);
    if (chosen.length === 0) return;
    setImporting(true);
    const base = importBaseUrl.trim();
    const prefix = importPrefix.trim();
    const results = await Promise.allSettled(
      chosen.map((m) =>
        api.post("/speech_to_text", {
          name: sanitizeName((prefix ? prefix + "-" : "") + m.id),
          class_name: "openai",
          privacy: "public",
          description: t("speechGen.import.importedDesc", { url: base }),
          enabled: true,
          options: { model: m.id, api_key: importApiKey, base_url: base },
        }, auth.user.token)
      )
    );
    const imported = results.filter((r) => r.status === "fulfilled").length;
    const skipped = results.length - imported;
    setImporting(false);
    toast.success(t("speechGen.import.done", { imported, skipped }));
    setImportOpen(false);
    fetchModels();
  };

  const columns = [
    {
      key: "name",
      label: t("speechGen.columns.name"),
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 32, height: 32, borderRadius: "8px",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: "rgba(14,165,233,0.12)",
            }}
          >
            <RecordVoiceOver sx={{ fontSize: 18, color: "#0ea5e9" }} />
          </Box>
          <Box sx={{ fontWeight: 500 }}>{row.name}</Box>
        </Box>
      ),
    },
    {
      key: "class_name",
      label: t("speechGen.columns.provider"),
      sortable: true,
      render: (row) => (
        <Chip size="small" label={row.class_name} sx={{ fontFamily: "monospace", fontSize: "0.72rem" }} />
      ),
    },
    {
      key: "model",
      label: t("speechGen.columns.model"),
      render: (row) => (
        <Box sx={{ fontFamily: "monospace", fontSize: "0.85rem", color: "text.secondary" }}>
          {row.options?.model || (row.class_name === "local" ? "(worker)" : "—")}
        </Box>
      ),
    },
    {
      key: "privacy",
      label: t("speechGen.columns.privacy"),
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
      label: t("speechGen.columns.enabled"),
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

  const enabledCount = models.filter((m) => m.enabled).length;

  return (
    <Container>
      <PageHero
        icon={<RecordVoiceOver sx={{ color: "#fff" }} />}
        eyebrow="SPEECH TO TEXT"
        title="Speech to Text"
        subtitle={t("speechGen.subtitle")}
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${models.length} configured` },
          { glyph: "★", color: "#7dd3fc", label: `${enabledCount} enabled` },
        ]}
        actions={
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              variant="outlined"
              startIcon={<PlayArrow />}
              onClick={() => navigate("/audio")}
              sx={{ color: "#fff", borderColor: "rgba(255,255,255,0.4)", "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" } }}
            >
              {t("speechGen.playground")}
            </Button>
            {isAdmin && (
              <Button
                variant="outlined"
                startIcon={<CloudDownload />}
                onClick={openImport}
                sx={{ color: "#fff", borderColor: "rgba(255,255,255,0.4)", "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" } }}
              >
                {t("speechGen.import.button")}
              </Button>
            )}
            {isAdmin && (
              <Button variant="contained" startIcon={<Add />} onClick={openCreate}>
                {t("speechGen.new")}
              </Button>
            )}
          </Box>
        }
      />

      <DataList
        data={models}
        columns={columns}
        searchKeys={["name", "class_name", "description"]}
        filters={[
          {
            key: "class_name",
            label: t("speechGen.columns.provider"),
            options: [
              { value: "local", label: "Local" },
              { value: "openai", label: "OpenAI" },
              { value: "google", label: "Google" },
              { value: "deepgram", label: "Deepgram" },
              { value: "assemblyai", label: "AssemblyAI" },
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
                <Tooltip title={t("speechGen.actions.edit")}>
                  <IconButton size="small" onClick={() => openEdit(row)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={row.class_name === "local" ? t("speechGen.actions.deleteLocal") : t("speechGen.actions.delete")}>
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
        emptyMessage={t("speechGen.empty")}
      />

      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{editing ? t("speechGen.dialog.editTitle", { name: editing.name }) : t("speechGen.dialog.newTitle")}</DialogTitle>
        <DialogContent>
          {editing?.class_name === "local" && (
            <Alert severity="info" sx={{ mb: 2 }}>
              {t("speechGen.dialog.localInfo", { name: editing.name })}
            </Alert>
          )}

          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <TextField
              label={t("speechGen.dialog.name")}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              disabled={!!editing}
              required
              helperText={editing ? "" : t("speechGen.dialog.nameHelp")}
              fullWidth
            />

            {(!editing || editing.class_name !== "local") && (
              <TextField
                select
                label={t("speechGen.dialog.provider")}
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
              label={t("speechGen.dialog.privacy")}
              value={form.privacy}
              onChange={(e) => setForm((f) => ({ ...f, privacy: e.target.value }))}
              fullWidth
            >
              <MenuItem value="public">{t("speechGen.dialog.privacyPublic")}</MenuItem>
              <MenuItem value="private">{t("speechGen.dialog.privacyPrivate")}</MenuItem>
            </TextField>

            <TextField
              label={t("speechGen.dialog.description")}
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
              <Typography variant="body2">{t("speechGen.dialog.enabled")}</Typography>
            </Box>

            {(!editing || editing.class_name !== "local") && (
              <>
                <Typography variant="subtitle2" sx={{ mt: 1 }}>{t("speechGen.dialog.providerOptions")}</Typography>
                <TextField
                  label={t("speechGen.dialog.apiKey")}
                  type="password"
                  value={form.options?.api_key ?? ""}
                  onChange={(e) => setOption("api_key", e.target.value)}
                  required={!editing}
                  fullWidth
                  helperText={editing ? t("speechGen.dialog.apiKeyHelp") : ""}
                />
                {(form.class_name === "openai" || form.class_name === "deepgram") && (
                  <TextField
                    label={t("speechGen.dialog.model")}
                    value={form.options?.model ?? ""}
                    onChange={(e) => setOption("model", e.target.value)}
                    required={form.class_name === "openai"}
                    fullWidth
                    helperText={
                      form.class_name === "openai"
                        ? "e.g. whisper-1, gpt-4o-transcribe, gpt-4o-mini-transcribe"
                        : "e.g. nova-2, enhanced, base"
                    }
                  />
                )}
                {form.class_name === "openai" && (
                  <TextField
                    label={t("speechGen.dialog.baseUrl")}
                    value={form.options?.base_url ?? ""}
                    onChange={(e) => setOption("base_url", e.target.value)}
                    fullWidth
                    placeholder="https://api.openai.com/v1"
                    helperText={t("speechGen.dialog.baseUrlHelp")}
                  />
                )}
                {form.class_name === "google" && (
                  <>
                    <TextField
                      label={t("speechGen.dialog.languageCode")}
                      value={form.options?.language_code ?? ""}
                      onChange={(e) => setOption("language_code", e.target.value)}
                      fullWidth
                      placeholder="en-US"
                    />
                    <TextField
                      label={t("speechGen.dialog.modelOptional")}
                      value={form.options?.model ?? ""}
                      onChange={(e) => setOption("model", e.target.value)}
                      fullWidth
                      placeholder="latest_long, telephony, …"
                    />
                  </>
                )}
                {form.class_name === "deepgram" && (
                  <TextField
                    label={t("speechGen.dialog.defaultLanguage")}
                    value={form.options?.language ?? ""}
                    onChange={(e) => setOption("language", e.target.value)}
                    fullWidth
                    placeholder="en"
                  />
                )}
                {form.class_name === "assemblyai" && (
                  <TextField
                    select
                    label={t("speechGen.dialog.speechModel")}
                    value={form.options?.speech_model ?? "best"}
                    onChange={(e) => setOption("speech_model", e.target.value)}
                    fullWidth
                  >
                    <MenuItem value="best">{t("speechGen.dialog.speechBest")}</MenuItem>
                    <MenuItem value="nano">{t("speechGen.dialog.speechNano")}</MenuItem>
                  </TextField>
                )}
              </>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={saving}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? t("speechGen.dialog.saving") : (editing ? t("speechGen.dialog.save") : t("speechGen.dialog.create"))}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={importOpen} onClose={closeImport} maxWidth="sm" fullWidth>
        <DialogTitle>{t("speechGen.import.title")}</DialogTitle>
        <DialogContent>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
            <Typography variant="body2" color="text.secondary">
              {t("speechGen.import.intro")}
            </Typography>

            <TextField
              label={t("speechGen.import.baseUrl")}
              value={importBaseUrl}
              onChange={(e) => setImportBaseUrl(e.target.value)}
              placeholder="https://api.openai.com/v1"
              helperText={t("speechGen.import.baseUrlHelp")}
              fullWidth
              disabled={discovering || importing}
            />
            <TextField
              label={t("speechGen.import.apiKey")}
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
                {discovering ? t("speechGen.import.discovering") : t("speechGen.import.discover")}
              </Button>
            </Box>

            {discovered && discovered.length > 0 && (
              <>
                <Divider />
                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <Typography variant="subtitle2">
                    {t("speechGen.import.modelsFound", { count: discovered.length })}
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
                    label={t("speechGen.import.selectAll")}
                  />
                </Box>
                <TextField
                  label={t("speechGen.import.prefix")}
                  value={importPrefix}
                  onChange={(e) => setImportPrefix(e.target.value)}
                  helperText={t("speechGen.import.prefixHelp")}
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
              <Alert severity="info">{t("speechGen.import.noModels")}</Alert>
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
              ? t("speechGen.import.importing")
              : t("speechGen.import.importSelected", { count: (discovered || []).filter((m) => selectedModels[m.id]).length })}
          </Button>
        </DialogActions>
      </Dialog>
    </Container>
  );
}
