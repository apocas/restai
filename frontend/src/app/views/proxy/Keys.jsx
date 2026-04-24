import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, CircularProgress, Divider, Grid,
  IconButton, MenuItem, Stack, styled, Table, TableBody, TableCell,
  TableHead, TableRow, TextField, Tooltip, Typography, useTheme,
  Autocomplete, Dialog, DialogActions, DialogContent, DialogTitle,
} from "@mui/material";
import RouteIcon from "@mui/icons-material/Route";
import KeyIcon from "@mui/icons-material/VpnKey";
import AddIcon from "@mui/icons-material/Add";
import DeleteIcon from "@mui/icons-material/Delete";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import CodeIcon from "@mui/icons-material/Code";
import { CopyBlock, monoBlue } from "react-code-blocks";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";

import Breadcrumb from "app/components/Breadcrumb";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } },
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" },
}));

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

export default function Proxy() {
  const { t } = useTranslation();
  const auth = useAuth();
  const { palette } = useTheme();
  const { platformCapabilities } = usePlatformCapabilities();

  const DURATIONS = [
    { value: "", label: t("proxy.durations.none") },
    { value: "1h", label: t("proxy.durations.hourly") },
    { value: "1d", label: t("proxy.durations.daily") },
    { value: "7d", label: t("proxy.durations.weekly") },
    { value: "30d", label: t("proxy.durations.monthly") },
  ];
  const [keys, setKeys] = useState([]);
  const [info, setInfo] = useState({ models: [], url: "" });
  const [loading, setLoading] = useState(true);

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createdKey, setCreatedKey] = useState(null);
  const [form, setForm] = useState({
    name: "", models: [],
    max_budget: "", duration_budget: "", rpm: "", tpm: "",
  });

  const fetchAll = () => {
    setLoading(true);
    return Promise.all([
      api.get("/proxy/keys", auth.user.token).then((d) => setKeys(d.keys || [])).catch(() => {}),
      api.get("/proxy/info", auth.user.token).then((d) => setInfo(d || { models: [], url: "" })).catch(() => {}),
    ]).finally(() => setLoading(false));
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("proxy.title");
    fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const handleDelete = (key_id, name) => {
    if (name === "default") {
      toast.error(t("proxy.cannotDeleteDefault"));
      return;
    }
    if (!window.confirm(t("proxy.deleteConfirm", { name }))) return;
    api.delete("/proxy/keys/" + key_id, auth.user.token)
      .then(() => { toast.success(t("proxy.keyDeleted")); fetchAll(); })
      .catch(() => {});
  };

  const openDialog = () => {
    setForm({ name: "", models: [], max_budget: "", duration_budget: "", rpm: "", tpm: "" });
    setCreatedKey(null);
    setDialogOpen(true);
  };

  const closeDialog = () => {
    setDialogOpen(false);
    setCreatedKey(null);
  };

  const handleCreate = () => {
    if (!form.name.trim()) { toast.error(t("proxy.nameRequired")); return; }
    if (!form.models || form.models.length === 0) { toast.error(t("proxy.modelRequired")); return; }

    setCreating(true);
    const payload = {
      name: form.name.trim(),
      models: form.models,
      max_budget: form.max_budget ? Number(form.max_budget) : null,
      duration_budget: form.duration_budget || null,
      rpm: form.rpm ? Number(form.rpm) : null,
      tpm: form.tpm ? Number(form.tpm) : null,
    };
    api.post("/proxy/keys", payload, auth.user.token)
      .then((response) => {
        toast.success(t("proxy.created"));
        setCreatedKey(response.key);
        fetchAll();
      })
      .catch(() => {})
      .finally(() => setCreating(false));
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success(t("common.copied"));
  };

  const proxyUrl = platformCapabilities?.proxy_url || info.url || "127.0.0.1";

  const usageCode = `from openai import OpenAI

client = OpenAI(
    api_key="YOUR_KEY",
    base_url="${proxyUrl}",
)

response = client.chat.completions.create(
    model="${(info.models && info.models[0]) || "model-name"}",
    messages=[{"role": "user", "content": "Hello"}],
)
print(response)`;

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("proxy.breadcrumb"), path: "/proxy/keys" }]} />
      </Box>

      <ContentBox>
        {/* Proxy Info */}
        <Card elevation={3} sx={{ mb: 3 }}>
          <FlexBox sx={{ p: 2 }}>
            <RouteIcon sx={{ mr: 1.5 }} />
            <H4>{t("proxy.info")}</H4>
          </FlexBox>
          <Divider />
          <Box sx={{ p: 2 }}>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <Typography variant="caption" color="text.secondary">{t("proxy.host")}</Typography>
                <Typography variant="body2" sx={{ wordBreak: "break-all" }}>
                  {platformCapabilities?.proxy_url || info.url || "—"}
                </Typography>
              </Grid>
              <Grid item xs={12}>
                <Typography variant="caption" color="text.secondary">{t("proxy.availableModels", { count: info.models.length })}</Typography>
                <Box sx={{ mt: 0.5, display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                  {info.models.length === 0 ? (
                    <Typography variant="body2" color="text.secondary">{t("proxy.noModels")}</Typography>
                  ) : info.models.map((model) => (
                    <Chip key={model} label={model} size="small" variant="outlined" color="primary" />
                  ))}
                </Box>
              </Grid>
            </Grid>
          </Box>
        </Card>

        {/* Keys Card */}
        <Card elevation={3} sx={{ mb: 3 }}>
          <FlexBox justifyContent="space-between" sx={{ pr: 2 }}>
            <FlexBox>
              <KeyIcon sx={{ ml: 2 }} />
              <H4 sx={{ p: 2 }}>{t("proxy.apiKeys")}</H4>
              <Typography variant="caption" color="text.secondary">
                {t("proxy.keys", { count: keys.length })}
              </Typography>
            </FlexBox>
            <Button
              variant="contained"
              size="small"
              startIcon={<AddIcon />}
              onClick={openDialog}
            >
              {t("proxy.newKey")}
            </Button>
          </FlexBox>
          <Divider />

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ pl: 2 }}>{t("proxy.columns.name")}</TableCell>
                <TableCell>{t("proxy.columns.key")}</TableCell>
                <TableCell>{t("proxy.columns.models")}</TableCell>
                <TableCell align="right">{t("proxy.columns.spend")}</TableCell>
                <TableCell align="right">{t("proxy.columns.budget")}</TableCell>
                <TableCell>{t("proxy.columns.duration")}</TableCell>
                <TableCell align="right">{t("proxy.columns.rpm")}</TableCell>
                <TableCell align="right">{t("proxy.columns.tpm")}</TableCell>
                <TableCell align="center" sx={{ pr: 2 }}>{t("proxy.columns.actions")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={9} align="center" sx={{ py: 4 }}>
                    <CircularProgress size={24} />
                  </TableCell>
                </TableRow>
              ) : keys.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} align="center" sx={{ py: 4 }}>
                    <Typography variant="body2" color="text.secondary">{t("proxy.noKeys")}</Typography>
                  </TableCell>
                </TableRow>
              ) : (
                keys.map((k) => (
                  <TableRow key={k.id} hover>
                    <TableCell sx={{ pl: 2, fontWeight: 500 }}>{k.name || "—"}</TableCell>
                    <TableCell>
                      <Box component="code" sx={{ fontSize: "0.75rem", color: "text.secondary" }}>
                        {k.key}
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5, maxWidth: 240 }}>
                        {(k.models || []).slice(0, 3).map((m, i) => (
                          <Chip key={i} label={m} size="small" variant="outlined" />
                        ))}
                        {(k.models || []).length > 3 && (
                          <Chip label={`+${k.models.length - 3}`} size="small" />
                        )}
                      </Box>
                    </TableCell>
                    <TableCell align="right">{(k.spend || 0).toFixed(3)} €</TableCell>
                    <TableCell align="right">{k.max_budget ? `${k.max_budget} €` : "—"}</TableCell>
                    <TableCell>{k.duration_budget || "—"}</TableCell>
                    <TableCell align="right">{k.rpm || "—"}</TableCell>
                    <TableCell align="right">{k.tpm || "—"}</TableCell>
                    <TableCell align="center" sx={{ pr: 2 }}>
                      <Tooltip title={t("proxy.deleteTip")}>
                        <IconButton size="small" onClick={() => handleDelete(k.id, k.name)}>
                          <DeleteIcon fontSize="small" color="error" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </Card>

        {/* Usage Example */}
        <Card elevation={3}>
          <FlexBox sx={{ pr: 2 }}>
            <CodeIcon sx={{ ml: 2 }} />
            <H4 sx={{ p: 2 }}>{t("proxy.usageExample")}</H4>
          </FlexBox>
          <Divider />
          <Box sx={{ p: 2 }}>
            <CopyBlock text={usageCode} language="python" theme={monoBlue} />
          </Box>
        </Card>
      </ContentBox>

      {/* New Key Dialog */}
      <Dialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>
          <FlexBox>
            <AddIcon sx={{ mr: 1 }} />
            {t("proxy.createTitle")}
          </FlexBox>
        </DialogTitle>
        <Divider />
        <DialogContent>
          {createdKey ? (
            <Stack spacing={2} sx={{ pt: 1 }}>
              <Typography variant="body2" color="text.secondary">
                {t("proxy.copyReveal")}
              </Typography>
              <Box
                sx={{
                  p: 2, bgcolor: "grey.100", borderRadius: 1,
                  display: "flex", alignItems: "center", justifyContent: "space-between", gap: 1,
                }}
              >
                <Box component="code" sx={{ fontSize: "0.85rem", wordBreak: "break-all" }}>
                  {createdKey}
                </Box>
                <Tooltip title={t("proxy.copyTip")}>
                  <IconButton size="small" onClick={() => copyToClipboard(createdKey)}>
                    <ContentCopyIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            </Stack>
          ) : (
            <Stack spacing={2} sx={{ pt: 1 }}>
              <TextField
                label={t("proxy.fieldName")}
                size="small"
                fullWidth
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                helperText={t("proxy.fieldNameHelp")}
              />

              <Autocomplete
                multiple
                size="small"
                options={info.models}
                value={form.models}
                onChange={(_, val) => setForm({ ...form, models: val })}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label={t("proxy.fieldModels")}
                    helperText={t("proxy.fieldModelsHelp")}
                  />
                )}
              />

              <Stack direction="row" spacing={2}>
                <TextField
                  label={t("proxy.fieldMaxBudget")}
                  size="small"
                  type="number"
                  fullWidth
                  value={form.max_budget}
                  onChange={(e) => setForm({ ...form, max_budget: e.target.value })}
                  helperText={t("proxy.fieldMaxBudgetHelp")}
                />
                <TextField
                  select
                  label={t("proxy.fieldBudgetReset")}
                  size="small"
                  fullWidth
                  value={form.duration_budget}
                  onChange={(e) => setForm({ ...form, duration_budget: e.target.value })}
                  helperText={t("proxy.fieldBudgetResetHelp")}
                >
                  {DURATIONS.map((d) => (
                    <MenuItem key={d.value} value={d.value}>{d.label}</MenuItem>
                  ))}
                </TextField>
              </Stack>

              <Stack direction="row" spacing={2}>
                <TextField
                  label={t("proxy.fieldRpm")}
                  size="small"
                  type="number"
                  fullWidth
                  value={form.rpm}
                  onChange={(e) => setForm({ ...form, rpm: e.target.value })}
                  helperText={t("proxy.fieldRpmHelp")}
                />
                <TextField
                  label={t("proxy.fieldTpm")}
                  size="small"
                  type="number"
                  fullWidth
                  value={form.tpm}
                  onChange={(e) => setForm({ ...form, tpm: e.target.value })}
                  helperText={t("proxy.fieldTpmHelp")}
                />
              </Stack>
            </Stack>
          )}
        </DialogContent>
        <Divider />
        <DialogActions>
          {createdKey ? (
            <Button onClick={closeDialog} variant="contained">{t("proxy.done")}</Button>
          ) : (
            <>
              <Button onClick={closeDialog}>{t("common.cancel")}</Button>
              <Button
                onClick={handleCreate}
                variant="contained"
                disabled={creating}
                startIcon={creating ? <CircularProgress size={16} color="inherit" /> : <AddIcon />}
              >
                {creating ? t("proxy.creating") : t("proxy.createKey")}
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>
    </Container>
  );
}
