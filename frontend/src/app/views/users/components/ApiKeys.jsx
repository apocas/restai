import { useState, useEffect } from "react";
import {
  Autocomplete,
  Box,
  Card,
  Button,
  Chip,
  Divider,
  FormControlLabel,
  IconButton,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  InputAdornment,
} from "@mui/material";
import { Delete, ContentCopy, Edit as EditIcon } from "@mui/icons-material";
import LinearProgress from "@mui/material/LinearProgress";

import { FlexBetween } from "app/components/FlexBox";
import { H5 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

export default function ApiKeys({ user }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [keys, setKeys] = useState([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [selectedProjects, setSelectedProjects] = useState([]);
  const [readOnly, setReadOnly] = useState(false);
  const [availableProjects, setAvailableProjects] = useState([]);
  const [newKey, setNewKey] = useState(null);
  // Quota-edit dialog state. We store the full key row so the dialog
  // can render current usage alongside the input field.
  const [quotaTarget, setQuotaTarget] = useState(null);
  const [quotaValue, setQuotaValue] = useState("");

  const handleEditQuota = (k) => {
    setQuotaTarget(k);
    setQuotaValue(k.token_quota_monthly != null ? String(k.token_quota_monthly) : "");
  };

  const submitQuota = (resetUsage = false) => {
    if (!quotaTarget) return;
    const body = {};
    if (resetUsage) body.reset_usage = true;
    else {
      const n = parseInt(quotaValue, 10);
      // Empty or 0 clears the cap (unlimited).
      body.token_quota_monthly = Number.isFinite(n) && n > 0 ? n : 0;
    }
    api.patch(`/users/${user.username}/apikeys/${quotaTarget.id}`, body, auth.user.token)
      .then(() => {
        setQuotaTarget(null);
        setQuotaValue("");
        fetchKeys();
        toast.success(resetUsage ? t("users.apiKeys.usageReset") : t("users.apiKeys.quotaSaved"), { position: "top-right" });
      })
      .catch(() => {});
  };

  const fetchKeys = () => {
    api.get("/users/" + user.username + "/apikeys", auth.user.token)
      .then((data) => setKeys(data))
      .catch(() => {});
  };

  const fetchProjects = () => {
    api.get("/projects", auth.user.token)
      .then((data) => setAvailableProjects(data.projects || []))
      .catch(() => {});
  };

  useEffect(() => {
    if (user.username) {
      fetchKeys();
      fetchProjects();
    }
  }, [user.username]);

  const handleCreate = () => {
    const body = { description, read_only: readOnly };
    if (selectedProjects.length > 0) {
      body.allowed_projects = selectedProjects.map(p => p.id);
    }
    api.post("/users/" + user.username + "/apikeys", body, auth.user.token)
      .then((data) => {
        setNewKey(data.api_key);
        setCreateOpen(false);
        setDescription("");
        setSelectedProjects([]);
        setReadOnly(false);
        fetchKeys();
      })
      .catch(() => {});
  };

  const handleDelete = (keyId) => {
    if (!window.confirm(t("users.apiKeys.deleteConfirm"))) return;
    api.delete("/users/" + user.username + "/apikeys/" + keyId, auth.user.token)
      .then(() => fetchKeys())
      .catch(() => {});
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success(t("common.copied"));
  };

  return (
    <>
      <Card>
        <FlexBetween px={3} py={2}>
          <H5>{t("users.apiKeys.title")}</H5>
          <Button variant="contained" onClick={() => setCreateOpen(true)}>
            {t("users.apiKeys.createNew")}
          </Button>
        </FlexBetween>

        <Divider />

        <TableContainer sx={{ p: 3 }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>{t("users.apiKeys.description")}</TableCell>
                <TableCell>{t("users.apiKeys.keyPrefix")}</TableCell>
                <TableCell>{t("users.apiKeys.scope")}</TableCell>
                <TableCell>{t("users.apiKeys.monthlyQuota")}</TableCell>
                <TableCell>{t("users.apiKeys.created")}</TableCell>
                <TableCell align="right">{t("users.apiKeys.actions")}</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {keys.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} align="center">
                    {t("users.apiKeys.noKeys")}
                  </TableCell>
                </TableRow>
              ) : (
                keys.map((k) => {
                  const used = k.tokens_used_this_month ?? 0;
                  const cap = k.token_quota_monthly;
                  const pct = cap ? Math.min(100, Math.round((used / cap) * 100)) : 0;
                  return (
                    <TableRow key={k.id}>
                      <TableCell>{k.description || "-"}</TableCell>
                      <TableCell><code>{k.key_prefix}...</code></TableCell>
                      <TableCell>
                        {k.read_only && (
                          <Chip label={t("users.apiKeys.readOnly")} size="small" color="warning" variant="outlined" sx={{ mr: 0.5 }} />
                        )}
                        {k.allowed_projects ? (
                          <Chip label={t("users.apiKeys.allowedProjects", { count: k.allowed_projects.length })} size="small" variant="outlined" />
                        ) : (
                          <Chip label={t("users.apiKeys.allProjects")} size="small" variant="outlined" />
                        )}
                      </TableCell>
                      <TableCell sx={{ minWidth: 200 }}>
                        {cap ? (
                          <Box>
                            <Typography variant="caption" sx={{ display: "block" }}>
                              {t("users.apiKeys.quotaTokens", { used: used.toLocaleString(), cap: cap.toLocaleString() })}
                            </Typography>
                            <LinearProgress
                              variant="determinate" value={pct}
                              color={pct >= 100 ? "error" : pct >= 80 ? "warning" : "primary"}
                              sx={{ mt: 0.5, height: 6, borderRadius: 1 }}
                            />
                            {k.quota_reset_at && (
                              <Typography variant="caption" color="text.secondary">
                                {t("users.apiKeys.quotaResets", { date: new Date(k.quota_reset_at).toLocaleDateString() })}
                              </Typography>
                            )}
                          </Box>
                        ) : (
                          <Typography variant="caption" color="text.secondary">{t("users.apiKeys.unlimited")}</Typography>
                        )}
                      </TableCell>
                      <TableCell>{new Date(k.created_at).toLocaleDateString()}</TableCell>
                      <TableCell align="right">
                        <Tooltip title={t("users.apiKeys.editQuota")}>
                          <IconButton onClick={() => handleEditQuota(k)}>
                            <EditIcon />
                          </IconButton>
                        </Tooltip>
                        <Tooltip title={t("common.delete")}>
                          <IconButton onClick={() => handleDelete(k.id)}>
                            <Delete color="error" />
                          </IconButton>
                        </Tooltip>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      {/* Create dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("users.apiKeys.createDialog")}</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label={t("users.apiKeys.descriptionOptional")}
            fullWidth
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <Autocomplete
            multiple
            options={availableProjects}
            getOptionLabel={(option) => option.name || t("users.apiKeys.projectLabel", { id: option.id })}
            value={selectedProjects}
            onChange={(e, newVal) => setSelectedProjects(newVal)}
            renderInput={(params) => (
              <TextField
                {...params}
                margin="dense"
                label={t("users.apiKeys.restrictProjects")}
                helperText={t("users.apiKeys.restrictHelp")}
              />
            )}
            sx={{ mt: 1 }}
          />
          <FormControlLabel
            control={<Switch checked={readOnly} onChange={(e) => setReadOnly(e.target.checked)} />}
            label={t("users.apiKeys.readOnlyCheckbox")}
            sx={{ mt: 1 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>{t("common.cancel")}</Button>
          <Button variant="contained" onClick={handleCreate}>{t("common.create")}</Button>
        </DialogActions>
      </Dialog>

      {/* Show new key dialog */}
      <Dialog open={!!newKey} onClose={() => setNewKey(null)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("users.apiKeys.saveKeyTitle")}</DialogTitle>
        <DialogContent>
          <Typography color="warning.main" sx={{ mb: 2 }}>
            {t("users.apiKeys.saveKeyWarn")}
          </Typography>
          <TextField
            fullWidth
            value={newKey || ""}
            InputProps={{
              readOnly: true,
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => copyToClipboard(newKey)}>
                    <ContentCopy />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button variant="contained" onClick={() => setNewKey(null)}>{t("common.done")}</Button>
        </DialogActions>
      </Dialog>

      {/* Quota edit dialog */}
      <Dialog open={!!quotaTarget} onClose={() => setQuotaTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>{t("users.apiKeys.quotaDialogTitle")}</DialogTitle>
        <DialogContent>
          {quotaTarget && (
            <>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                {t("users.apiKeys.quotaUsedThis", { prefix: quotaTarget.key_prefix, used: (quotaTarget.tokens_used_this_month ?? 0).toLocaleString() })}
              </Typography>
              <TextField
                autoFocus fullWidth type="number"
                label={t("users.apiKeys.quotaInput")}
                value={quotaValue}
                onChange={(e) => setQuotaValue(e.target.value)}
                helperText={t("users.apiKeys.quotaInputHelper")}
                inputProps={{ min: 0, step: 1000 }}
              />
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setQuotaTarget(null)}>{t("common.cancel")}</Button>
          <Button onClick={() => submitQuota(true)} color="warning">{t("users.apiKeys.resetUsage")}</Button>
          <Button variant="contained" onClick={() => submitQuota(false)}>{t("common.save")}</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
