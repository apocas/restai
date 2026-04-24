import { Card, Chip, Grid, TextField, Button, MenuItem, Switch, Slider, Typography, IconButton, Divider, Box, Tooltip, Table, TableHead, TableBody, TableRow, TableCell } from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import { HelpOutline } from "@mui/icons-material";
import FormControlLabel from "@mui/material/FormControlLabel";
import { Fragment, useState, useEffect, useCallback } from "react";
import { toast } from "react-toastify";
import api from "app/utils/api";
import { useTranslation } from "react-i18next";
import { makeErrorFor } from "./projectOptionValidators";

// Status → chip color. Mirror of the server-side status enum in
// BulkIngestJobDatabase (queued/processing/done/error).
const BULK_STATUS_COLOR = {
  queued: "default",
  processing: "info",
  done: "success",
  error: "error",
};

const HelpTip = ({ text }) => (
  <Tooltip title={text} placement="top" arrow>
    <HelpOutline sx={{ fontSize: 16, color: "text.disabled", ml: 0.5, cursor: "help", verticalAlign: "middle" }} />
  </Tooltip>
);

export default function ProjectEditKnowledge({ state, setState, handleChange, project, auth, fieldErrors = {}, clearFieldError = () => {} }) {
  // All hooks must be called unconditionally (rules-of-hooks). Early
  // returns for non-RAG happen AFTER this block.
  const { t } = useTranslation();
  const errorFor = makeErrorFor(fieldErrors, state);

  // Bulk ingest job list + uploader state. Polled every 5s while the
  // tab is mounted so the admin sees status flip from queued →
  // processing → done without a manual reload.
  const [bulkJobs, setBulkJobs] = useState([]);
  const [uploading, setUploading] = useState(false);

  const refreshJobs = useCallback(() => {
    if (!project?.id) return;
    api.get(`/projects/${project.id}/ingest-bulk?limit=20`, auth.user.token, { silent: true })
      .then((d) => setBulkJobs(d.jobs || []))
      .catch(() => {});
  }, [project?.id, auth.user.token]);

  useEffect(() => {
    // Only poll for RAG projects — other types never read this tab.
    if (state.type !== "rag") return undefined;
    refreshJobs();
    const t = setInterval(refreshJobs, 5000);
    return () => clearInterval(t);
  }, [refreshJobs, state.type]);

  if (state.type !== "rag") return null;

  const handleBulkUpload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (files.length === 0 || !project?.id) return;
    setUploading(true);
    try {
      const form = new FormData();
      for (const f of files) form.append("files", f);
      await api.post(
        `/projects/${project.id}/ingest-bulk?method=auto&splitter=sentence&chunks=256`,
        form,
        auth.user.token,
      );
      toast.success(t("projects.edit.knowledge.queuedFiles", { count: files.length }), { position: "top-right" });
      refreshJobs();
    } catch (err) {
      // api.js toasts already; no-op
    } finally {
      setUploading(false);
      // Reset the input so re-uploading the same file works.
      e.target.value = "";
    }
  };

  const handleCancelJob = (jobId) => {
    api.delete(`/projects/${project.id}/ingest-bulk/${jobId}`, auth.user.token)
      .then(() => refreshJobs())
      .catch(() => {});
  };

  return (
    <Grid container spacing={3}>
      {/* Bulk ingest queue */}
      <Grid item sm={12} xs={12}>
        <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
          {t("projects.edit.knowledge.bulkIngest")}
          <HelpTip text="Upload one or more files and the ingest cron will process them in the background. Poll the table below for status." />
        </Typography>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", mb: 2, flexWrap: "wrap" }}>
          <Button
            variant="contained" size="small" startIcon={<CloudUploadIcon />}
            component="label" disabled={uploading}
          >
            {uploading ? t("projects.edit.knowledge.uploading") : t("projects.edit.knowledge.uploadFiles")}
            <input type="file" hidden multiple onChange={handleBulkUpload} />
          </Button>
          <Typography variant="caption" color="text.secondary">
            {t("projects.edit.knowledge.ingestHelp")}
          </Typography>
        </Box>
        {bulkJobs.length > 0 && (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>File</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Docs</TableCell>
                <TableCell align="right">Chunks</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {bulkJobs.map((job) => (
                <TableRow key={job.id}>
                  <TableCell>
                    <Typography variant="body2">{job.filename}</Typography>
                    {job.error_message && (
                      <Typography variant="caption" color="error" sx={{ display: "block" }}>
                        {job.error_message}
                      </Typography>
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip size="small" label={job.status} color={BULK_STATUS_COLOR[job.status] || "default"} />
                  </TableCell>
                  <TableCell align="right">{job.documents_count ?? "—"}</TableCell>
                  <TableCell align="right">{job.chunks_count ?? "—"}</TableCell>
                  <TableCell align="right">
                    <IconButton size="small" onClick={() => handleCancelJob(job.id)} title="Delete row">
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <Divider sx={{ mt: 2 }} />
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>
      <Grid item sm={6} xs={12}>
        <Typography id="discrete-slider" gutterBottom>
          K Value<HelpTip text="Number of document chunks retrieved per query. Higher values provide more context but increase latency and cost" />
        </Typography>
        <Slider
          name="k"
          value={state.options?.k ?? 4}
          onChange={handleChange}
          aria-labelledby="input-slider"
          step={1}
          min={0}
          max={10}
          valueLabelDisplay="auto"
          style={{ width: "400px" }}
        />
      </Grid>
      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="score"
          label={t("projects.edit.knowledge.scoreHint").split(".")[0]}
          helperText={errorFor("score") || "Minimum relevance score (0-1) a chunk must have. Higher = stricter, may miss useful context"}
          error={!!errorFor("score")}
          variant="outlined"
          onChange={(e) => { clearFieldError("score"); handleChange(e); }}
          value={state.options?.score ?? ''}
        />
      </Grid>
      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label={<span>LLM Rerank<HelpTip text="Uses the LLM to re-score and reorder retrieved chunks by relevance. More accurate but adds an extra LLM call per query" /></span>}
          control={
            <Switch
              checked={state.options?.llm_rerank ?? false}
              name="llm_rerank"
              inputProps={{ "aria-label": "llm rerank checkbox" }}
              onChange={handleChange}
            />
          }
        />
      </Grid>
      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label={<span>Colbert Rerank<HelpTip text="Uses a ColBERT model to rerank retrieved chunks. Faster than LLM rerank with good accuracy, runs locally" /></span>}
          control={
            <Switch
              checked={state.options?.colbert_rerank ?? false}
              name="colbert_rerank"
              inputProps={{ "aria-label": "colbert rerank checkbox" }}
              onChange={handleChange}
            />
          }
        />
      </Grid>
      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>
      <Grid item sm={12} xs={12}>
        <Typography variant="subtitle1" gutterBottom>Knowledge Graph</Typography>
        <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
          Extract entities (people, organizations, places) during ingestion. Enables entity-aware retrieval, a visual graph explorer, and natural language graph queries. Adds processing time to ingestion.
        </Typography>
      </Grid>
      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label={<span>Enable Knowledge Graph<HelpTip text="Runs Named Entity Recognition on every ingested document and stores entities in a queryable graph. Off by default — adds CPU/memory overhead during ingestion." /></span>}
          control={
            <Switch
              checked={state.options?.enable_knowledge_graph ?? false}
              name="enable_knowledge_graph"
              onChange={handleChange}
            />
          }
        />
      </Grid>
      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>
      <Grid item sm={12} xs={12}>
        <Typography variant="subtitle1" gutterBottom>Natural Language to SQL</Typography>
        <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
          Connect a database to translate natural language questions into SQL queries automatically.
        </Typography>
      </Grid>
      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="connection"
          label="Database Connection String"
          variant="outlined"
          onChange={handleChange}
          value={state.options?.connection ?? ''}
          placeholder="mysql://user:pass@host/db or postgresql://user:pass@host/db"
          helperText="MySQL or PostgreSQL connection string"
        />
      </Grid>
      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="tables"
          label="Allowed Tables"
          variant="outlined"
          onChange={handleChange}
          value={state.options?.tables ?? ''}
          placeholder="users, orders, products"
          helperText="Comma-separated list of tables to allow (leave empty for all)"
        />
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
        <Typography variant="subtitle2" color="text.secondary" sx={{ mt: 1 }}>Knowledge Base Sync</Typography>
      </Grid>
      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label="Auto-Sync Enabled"
          control={
            <Switch
              checked={state.options?.sync_enabled ?? false}
              onChange={(e) => setState({ ...state, options: { ...state.options, sync_enabled: e.target.checked } })}
            />
          }
        />
      </Grid>
      {state.options?.sync_enabled && (
        <>
          {(state.options?.sync_sources || []).map((src, idx) => (
            <Grid item xs={12} key={idx}>
              <Card variant="outlined" sx={{ p: 2 }}>
                <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
                  <Typography variant="subtitle2">Source #{idx + 1}</Typography>
                  <IconButton size="small" color="error" onClick={() => {
                    const updated = [...(state.options.sync_sources || [])];
                    updated.splice(idx, 1);
                    setState({ ...state, options: { ...state.options, sync_sources: updated } });
                  }}><DeleteIcon fontSize="small" /></IconButton>
                </Box>
                <Grid container spacing={2}>
                  <Grid item xs={12} sm={4}>
                    <TextField
                      fullWidth select size="small" label="Type"
                      value={src.type || "url"}
                      onChange={(e) => {
                        const updated = [...state.options.sync_sources];
                        updated[idx] = { ...updated[idx], type: e.target.value };
                        setState({ ...state, options: { ...state.options, sync_sources: updated } });
                      }}
                    >
                      <MenuItem value="url">Web URL</MenuItem>
                      <MenuItem value="s3">Amazon S3</MenuItem>
                      <MenuItem value="confluence">Confluence</MenuItem>
                      <MenuItem value="sharepoint">SharePoint</MenuItem>
                      <MenuItem value="gdrive">Google Drive</MenuItem>
                    </TextField>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField
                      fullWidth size="small" label="Name"
                      value={src.name || ""}
                      onChange={(e) => {
                        const updated = [...state.options.sync_sources];
                        updated[idx] = { ...updated[idx], name: e.target.value };
                        setState({ ...state, options: { ...state.options, sync_sources: updated } });
                      }}
                      helperText="Identifier for this source"
                    />
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField
                      fullWidth select size="small"
                      label="Splitter"
                      helperText="Sentence preserves natural boundaries, Token splits by fixed count"
                      value={src.splitter || "sentence"}
                      onChange={(e) => {
                        const updated = [...state.options.sync_sources];
                        updated[idx] = { ...updated[idx], splitter: e.target.value };
                        setState({ ...state, options: { ...state.options, sync_sources: updated } });
                      }}
                    >
                      <MenuItem value="sentence">Sentence</MenuItem>
                      <MenuItem value="token">Token</MenuItem>
                    </TextField>
                  </Grid>
                  <Grid item xs={12} sm={4}>
                    <TextField
                      fullWidth select size="small" label="Sync Interval"
                      value={src.sync_interval || 60}
                      onChange={(e) => {
                        const updated = [...state.options.sync_sources];
                        updated[idx] = { ...updated[idx], sync_interval: parseInt(e.target.value) };
                        setState({ ...state, options: { ...state.options, sync_sources: updated } });
                      }}
                    >
                      {[
                        { value: 15, label: "Every 15 min" },
                        { value: 30, label: "Every 30 min" },
                        { value: 60, label: "Every hour" },
                        { value: 360, label: "Every 6 hours" },
                        { value: 720, label: "Every 12 hours" },
                        { value: 1440, label: "Every 24 hours" },
                      ].map((opt) => (
                        <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                      ))}
                    </TextField>
                  </Grid>
                  {src.type === "url" && (
                    <Grid item xs={12}>
                      <TextField
                        fullWidth size="small" label="URL"
                        value={src.url || ""}
                        onChange={(e) => {
                          const updated = [...state.options.sync_sources];
                          updated[idx] = { ...updated[idx], url: e.target.value };
                          setState({ ...state, options: { ...state.options, sync_sources: updated } });
                        }}
                        placeholder="https://example.com/docs"
                      />
                    </Grid>
                  )}
                  {src.type === "s3" && (
                    <>
                      <Grid item xs={12} sm={4}>
                        <TextField fullWidth size="small" label="S3 Bucket" value={src.s3_bucket || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], s3_bucket: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} />
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <TextField fullWidth size="small" label="Prefix (folder)" value={src.s3_prefix || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], s3_prefix: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="docs/" />
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <TextField fullWidth size="small" label="Region" value={src.s3_region || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], s3_region: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="us-east-1" />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Access Key" type="password" value={src.s3_access_key || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], s3_access_key: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Secret Key" type="password" value={src.s3_secret_key || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], s3_secret_key: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} />
                      </Grid>
                    </>
                  )}
                  {src.type === "confluence" && (
                    <>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Base URL" value={src.confluence_base_url || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], confluence_base_url: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="https://yoursite.atlassian.net" />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Space Key" value={src.confluence_space_key || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], confluence_space_key: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="ENG" />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Email" value={src.confluence_email || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], confluence_email: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="user@company.com" />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="API Token" type="password" value={src.confluence_api_token || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], confluence_api_token: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} />
                      </Grid>
                    </>
                  )}
                  {src.type === "sharepoint" && (
                    <>
                      <Grid item xs={12} sm={4}>
                        <TextField fullWidth size="small" label="Tenant ID" value={src.sharepoint_tenant_id || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], sharepoint_tenant_id: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" />
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <TextField fullWidth size="small" label="Client ID" value={src.sharepoint_client_id || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], sharepoint_client_id: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} />
                      </Grid>
                      <Grid item xs={12} sm={4}>
                        <TextField fullWidth size="small" label="Client Secret" type="password" value={src.sharepoint_client_secret || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], sharepoint_client_secret: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Site Name" value={src.sharepoint_site_name || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], sharepoint_site_name: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="MySite" helperText="From yourorg.sharepoint.com/sites/MySite" />
                      </Grid>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Folder Path (optional)" value={src.sharepoint_folder || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], sharepoint_folder: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="General/Docs" helperText="Leave empty for all files in the document library" />
                      </Grid>
                    </>
                  )}
                  {src.type === "gdrive" && (
                    <>
                      <Grid item xs={12} sm={6}>
                        <TextField fullWidth size="small" label="Folder ID" value={src.gdrive_folder_id || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], gdrive_folder_id: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder="1AbC_dEfGhIjKlMnOpQrStUv"
                          helperText="From the folder URL: drive.google.com/drive/folders/{ID}" />
                      </Grid>
                      <Grid item xs={12}>
                        <TextField fullWidth size="small" label="Service Account JSON" multiline rows={3}
                          value={src.gdrive_service_account_json || ""}
                          onChange={(e) => {
                            const updated = [...state.options.sync_sources];
                            updated[idx] = { ...updated[idx], gdrive_service_account_json: e.target.value };
                            setState({ ...state, options: { ...state.options, sync_sources: updated } });
                          }} placeholder='{"type": "service_account", ...}'
                          helperText="Paste the full JSON key from Google Cloud Console. Share the Drive folder with the service account email." />
                      </Grid>
                    </>
                  )}
                </Grid>
              </Card>
            </Grid>
          ))}
          <Grid item xs={12}>
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button variant="outlined" size="small" onClick={() => {
                const sources = [...(state.options?.sync_sources || []), { type: "url", name: "", url: "", splitter: "sentence", chunks: 512 }];
                setState({ ...state, options: { ...state.options, sync_sources: sources } });
              }}>
                Add Source
              </Button>
              <Button variant="outlined" size="small" color="secondary" onClick={() => {
                api.post(`/projects/${project.id}/sync/trigger`, {}, auth.user.token)
                  .then(() => alert("Sync triggered"))
                  .catch(() => {});
              }}>
                Sync Now
              </Button>
            </Box>
          </Grid>
        </>
      )}
    </Grid>
  );
}
