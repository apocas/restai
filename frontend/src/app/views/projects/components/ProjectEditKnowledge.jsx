import { Card, Grid, TextField, Button, MenuItem, Switch, Slider, Typography, IconButton, Divider, Box } from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import FormControlLabel from "@mui/material/FormControlLabel";
import { Fragment } from "react";
import api from "app/utils/api";

export default function ProjectEditKnowledge({ state, setState, handleChange, project, auth }) {
  if (state.type !== "rag") return null;

  return (
    <Grid container spacing={3}>
      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>
      <Grid item sm={6} xs={12}>
        <Typography id="discrete-slider" gutterBottom>
          K Value
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
          label="Cutoff Score"
          variant="outlined"
          onChange={handleChange}
          value={state.options?.score ?? ''}
        />
      </Grid>
      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label="LLM Rerank"
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
          label="Colbert Rerank"
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
        <Grid item sm={6} xs={12}>
          <TextField
            fullWidth select size="small"
            label="Sync Interval"
            value={state.options?.sync_interval ?? 60}
            onChange={(e) => setState({ ...state, options: { ...state.options, sync_interval: parseInt(e.target.value) } })}
          >
            {[
              { value: 15, label: "Every 15 minutes" },
              { value: 30, label: "Every 30 minutes" },
              { value: 60, label: "Every hour" },
              { value: 360, label: "Every 6 hours" },
              { value: 720, label: "Every 12 hours" },
              { value: 1440, label: "Every 24 hours" },
            ].map((opt) => (
              <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
            ))}
          </TextField>
        </Grid>
      )}
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
                      fullWidth select size="small" label="Splitter"
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
