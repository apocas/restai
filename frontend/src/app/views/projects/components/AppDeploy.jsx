import { useState, useEffect, useCallback, useRef } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Divider,
  FormControl,
  FormControlLabel,
  Grid,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  TextField,
  Tooltip,
  Typography,
  styled,
} from "@mui/material";
import {
  CloudUpload,
  Download,
  NetworkCheck,
  Save,
} from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Pane = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(2),
  display: "flex",
  flexDirection: "column",
  gap: theme.spacing(1.5),
  minHeight: 320,
}));

const LogBox = styled(Paper)(({ theme }) => ({
  marginTop: theme.spacing(1),
  padding: theme.spacing(1),
  fontFamily: "ui-monospace, Menlo, Consolas, monospace",
  fontSize: "0.78rem",
  background: theme.palette.mode === "dark" ? "#0a0a0a" : "#fafafa",
  color: theme.palette.mode === "dark" ? "#e0e0e0" : "#222",
  maxHeight: 280,
  overflow: "auto",
  whiteSpace: "pre-wrap",
  border: `1px solid ${theme.palette.divider}`,
}));

const apiBase = process.env.REACT_APP_RESTAI_API_URL || "";

// Pretty timestamp for the log box.
function ts() {
  return new Date().toISOString().slice(11, 19);
}

export default function AppDeploy({ projectId, project, token, onProjectReload }) {
  const { t } = useTranslation();

  // Saved options on the project — initial values for the form.
  const opts = project?.options || {};
  const [form, setForm] = useState({
    protocol: opts.ftp_protocol || "sftp",
    host: opts.ftp_host || "",
    port: opts.ftp_port || "",
    user: opts.ftp_user || "",
    password: "", // never pre-fill (the API returns a "****" mask)
    path: opts.ftp_path || "/",
    use_passive: opts.ftp_use_passive !== false,
  });
  const [includeSource, setIncludeSource] = useState(false);
  const [includeDb, setIncludeDb] = useState(false);

  const [savingCreds, setSavingCreds] = useState(false);
  const [testing, setTesting] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [log, setLog] = useState([]); // [{ts, type, text}]
  const abortRef = useRef(null);

  // Re-seed the form whenever the parent re-fetches the project (e.g. after
  // a successful save) so the displayed values match what's persisted.
  useEffect(() => {
    if (!project) return;
    const o = project.options || {};
    setForm((prev) => ({
      ...prev,
      protocol: o.ftp_protocol || "sftp",
      host: o.ftp_host || "",
      port: o.ftp_port || "",
      user: o.ftp_user || "",
      path: o.ftp_path || "/",
      use_passive: o.ftp_use_passive !== false,
      // Don't overwrite password: the API masks it on read, and the user
      // may have typed a fresh value.
    }));
  }, [project]);

  const setField = (name, value) => setForm((prev) => ({ ...prev, [name]: value }));

  const appendLog = useCallback((type, text) => {
    setLog((prev) => [...prev, { ts: ts(), type, text }].slice(-200));
  }, []);

  // ---- Save credentials ------------------------------------------------
  const saveCredentials = useCallback(async () => {
    setSavingCreds(true);
    try {
      // Don't PATCH the password if the user didn't change it (the API
      // serves the saved value as "****..." and the project-edit router
      // preserves untouched mask values on PATCH).
      const optionsPatch = {
        ftp_protocol: form.protocol,
        ftp_host: form.host,
        ftp_port: form.port ? Number(form.port) : null,
        ftp_user: form.user,
        ftp_path: form.path,
        ftp_use_passive: form.use_passive,
      };
      if (form.password) {
        optionsPatch.ftp_password = form.password;
      }
      // PATCH /projects/{id} expects {options: {...}} merged into existing
      // options (the router preserves keys not sent).
      await api.patch(`/projects/${projectId}`, { options: optionsPatch }, token);
      toast.success(t("projects.app.deploy.saved", "Deploy settings saved"));
      // Clear the password field — it's now persisted, no point keeping it
      // in component state where it could leak to a future submit.
      setForm((prev) => ({ ...prev, password: "" }));
      if (onProjectReload) onProjectReload();
    } catch (e) {
      toast.error(e?.message || "save failed");
    } finally {
      setSavingCreds(false);
    }
  }, [projectId, token, form, t, onProjectReload]);

  // ---- Test connection -------------------------------------------------
  const testConnection = useCallback(async () => {
    if (!form.host) {
      toast.error(t("projects.app.deploy.hostRequired", "Host is required"));
      return;
    }
    setTesting(true);
    appendLog("test", `→ test ${form.protocol}://${form.user}@${form.host}:${form.port || (form.protocol === 'sftp' ? 22 : 21)}${form.path}`);
    try {
      const res = await api.post(
        `/projects/${projectId}/app/deploy/test`,
        {
          protocol: form.protocol,
          host: form.host,
          port: form.port ? Number(form.port) : null,
          user: form.user,
          password: form.password || "", // empty = use saved
          path: form.path,
          use_passive: form.use_passive,
        },
        token
      );
      if (res.ok) {
        toast.success(res.message || t("projects.app.deploy.connected", "Connected"));
        appendLog("ok", `✓ ${res.message}`);
      } else {
        toast.error(res.error || "test failed");
        appendLog("error", `✗ ${res.error}`);
      }
    } catch (e) {
      toast.error(e?.message || "test failed");
      appendLog("error", `✗ ${e?.message || e}`);
    } finally {
      setTesting(false);
    }
  }, [projectId, token, form, t, appendLog]);

  // ---- Download zip ----------------------------------------------------
  // Triggered by a plain anchor click — letting the browser handle the
  // streaming download is simpler than wrestling with fetch + Blob, and
  // it shows the download progress in the browser's UI for free.
  const downloadHref = `${apiBase}/projects/${projectId}/app/download?include_source=${includeSource}&include_db=${includeDb}`;

  // ---- Deploy with SSE -------------------------------------------------
  const startDeploy = useCallback(() => {
    if (deploying) return;
    setDeploying(true);
    setLog([]);
    appendLog("info", `→ deploy ${form.protocol}://${form.user}@${form.host}:${form.port || (form.protocol === 'sftp' ? 22 : 21)}${form.path}`);

    const controller = new AbortController();
    abortRef.current = controller;

    const body = JSON.stringify({
      include_source: includeSource,
      include_db: includeDb,
      // Send overrides so the user can do an ad-hoc deploy without saving.
      protocol: form.protocol,
      host: form.host,
      port: form.port ? Number(form.port) : null,
      user: form.user,
      password: form.password || undefined, // undefined → router falls back to saved
      path: form.path,
      use_passive: form.use_passive,
    });

    // We need SSE WITH a POST body and Authorization header — the native
    // EventSource doesn't support either. Use fetch + ReadableStream and
    // parse `event:` / `data:` frames by hand.
    fetch(`${apiBase}/projects/${projectId}/app/deploy`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Basic " + token,
        "Accept": "text/event-stream",
      },
      body,
      signal: controller.signal,
    }).then(async (res) => {
      if (!res.ok) {
        const txt = await res.text();
        appendLog("error", `✗ HTTP ${res.status}: ${txt}`);
        toast.error(`HTTP ${res.status}`);
        setDeploying(false);
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          let evt = "message", data = null;
          for (const line of frame.split("\n")) {
            if (line.startsWith("event:")) evt = line.slice(6).trim();
            else if (line.startsWith("data:")) {
              try { data = JSON.parse(line.slice(5).trim()); } catch { /* ignore */ }
            }
          }
          if (evt === "upload" && data) {
            appendLog("upload", `↑ [${data.index}/${data.total}] ${data.path}`);
          } else if (evt === "connect" && data) {
            appendLog("info", data.message || "connecting");
          } else if (evt === "mkdir" && data) {
            appendLog("info", data.message || "");
          } else if (evt === "done" && data) {
            appendLog("ok", `✓ uploaded ${data.uploaded} file(s) to ${data.remote_dir}`);
            toast.success(t("projects.app.deploy.done", "Deploy finished — {{count}} file(s) uploaded", { count: data.uploaded }));
          } else if (evt === "error" && data) {
            appendLog("error", `✗ ${data.message}`);
            toast.error(data.message || "deploy failed");
          }
        }
      }
    }).catch((e) => {
      if (e?.name !== "AbortError") {
        appendLog("error", `✗ ${e?.message || e}`);
        toast.error(e?.message || "deploy failed");
      }
    }).finally(() => {
      setDeploying(false);
      abortRef.current = null;
    });
  }, [projectId, token, form, includeSource, includeDb, deploying, appendLog, t]);

  const cancelDeploy = useCallback(() => {
    if (abortRef.current) abortRef.current.abort();
    appendLog("info", "deploy cancelled");
    setDeploying(false);
  }, [appendLog]);

  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "1fr 1fr" }, gap: 2, minHeight: "60vh" }}>
      {/* Download (no creds needed) */}
      <Pane variant="outlined">
        <Typography variant="subtitle2">
          <Download fontSize="small" sx={{ verticalAlign: "middle", mr: 1 }} />
          {t("projects.app.deploy.downloadTitle", "Download as ZIP")}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t(
            "projects.app.deploy.downloadHelp",
            "Grab a zip of your generated app. Drop it on any cheap PHP host that supports PHP 8 with PDO SQLite — no Composer, no Node, no other dependencies."
          )}
        </Typography>
        <FormControlLabel
          control={<Checkbox checked={includeSource} onChange={(e) => setIncludeSource(e.target.checked)} />}
          label={t("projects.app.deploy.includeSource", "Include TypeScript source (src/) — typically not needed in production")}
        />
        <FormControlLabel
          control={<Checkbox checked={includeDb} onChange={(e) => setIncludeDb(e.target.checked)} />}
          label={t("projects.app.deploy.includeDb", "Include database.sqlite — risky, may overwrite production data on extraction")}
        />
        <Box>
          <Button
            variant="contained"
            startIcon={<Download />}
            href={downloadHref}
            // Anchor needs Basic auth in the URL? No — same-origin admin
            // session cookies authenticate the request. (token is the
            // Basic header; the server accepts the session cookie too.)
            target="_blank"
            rel="noopener noreferrer"
          >
            {t("projects.app.deploy.downloadButton", "Download ZIP")}
          </Button>
        </Box>
      </Pane>

      {/* Deploy via FTP/SFTP */}
      <Pane variant="outlined">
        <Typography variant="subtitle2">
          <CloudUpload fontSize="small" sx={{ verticalAlign: "middle", mr: 1 }} />
          {t("projects.app.deploy.deployTitle", "Push to host (FTP / SFTP)")}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t(
            "projects.app.deploy.deployHelp",
            "Configure your shared host's FTP/SFTP credentials. RESTai stores the password encrypted at rest and never logs it."
          )}
        </Typography>

        <Grid container spacing={1.5}>
          <Grid item xs={6} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>{t("projects.app.deploy.protocol", "Protocol")}</InputLabel>
              <Select
                label={t("projects.app.deploy.protocol", "Protocol")}
                value={form.protocol}
                onChange={(e) => setField("protocol", e.target.value)}
              >
                <MenuItem value="sftp">SFTP</MenuItem>
                <MenuItem value="ftp">FTP</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={6} sm={5}>
            <TextField
              size="small"
              fullWidth
              label={t("projects.app.deploy.host", "Host")}
              value={form.host}
              onChange={(e) => setField("host", e.target.value)}
              placeholder="example.com"
            />
          </Grid>
          <Grid item xs={4} sm={3}>
            <TextField
              size="small"
              fullWidth
              label={t("projects.app.deploy.port", "Port")}
              value={form.port}
              onChange={(e) => setField("port", e.target.value.replace(/[^0-9]/g, ""))}
              placeholder={form.protocol === "sftp" ? "22" : "21"}
            />
          </Grid>
          <Grid item xs={6}>
            <TextField
              size="small"
              fullWidth
              label={t("projects.app.deploy.user", "Username")}
              value={form.user}
              onChange={(e) => setField("user", e.target.value)}
            />
          </Grid>
          <Grid item xs={6}>
            <TextField
              size="small"
              fullWidth
              type="password"
              label={t("projects.app.deploy.password", "Password")}
              value={form.password}
              onChange={(e) => setField("password", e.target.value)}
              placeholder={opts.ftp_password ? "••••••" : ""}
              helperText={opts.ftp_password
                ? t("projects.app.deploy.passwordSavedHelp", "Leave blank to keep saved password")
                : t("projects.app.deploy.passwordEncryptedHelp", "Encrypted at rest")
              }
            />
          </Grid>
          <Grid item xs={12} sm={9}>
            <TextField
              size="small"
              fullWidth
              label={t("projects.app.deploy.path", "Remote directory")}
              value={form.path}
              onChange={(e) => setField("path", e.target.value)}
              placeholder="/var/www/html"
            />
          </Grid>
          <Grid item xs={12} sm={3}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.use_passive}
                  onChange={(e) => setField("use_passive", e.target.checked)}
                  disabled={form.protocol === "sftp"}
                />
              }
              label={t("projects.app.deploy.passive", "Passive (FTP)")}
            />
          </Grid>
        </Grid>

        {form.protocol === "ftp" && (
          <Alert severity="warning">
            {t(
              "projects.app.deploy.ftpClearText",
              "FTP transmits your credentials in cleartext. Prefer SFTP if your host supports it."
            )}
          </Alert>
        )}

        <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", gap: 1 }}>
          <Tooltip title={t("projects.app.deploy.saveTip", "Persist credentials on the project (encrypted at rest)")}>
            <span>
              <Button
                size="small"
                variant="outlined"
                startIcon={savingCreds ? <CircularProgress size={14} /> : <Save />}
                onClick={saveCredentials}
                disabled={savingCreds || !form.host || !form.user}
              >
                {t("projects.app.deploy.save", "Save")}
              </Button>
            </span>
          </Tooltip>
          <Button
            size="small"
            variant="outlined"
            startIcon={testing ? <CircularProgress size={14} /> : <NetworkCheck />}
            onClick={testConnection}
            disabled={testing || !form.host || !form.user}
          >
            {t("projects.app.deploy.test", "Test connection")}
          </Button>
          {deploying ? (
            <Button size="small" variant="contained" color="warning" onClick={cancelDeploy}>
              {t("projects.app.deploy.cancel", "Cancel")}
            </Button>
          ) : (
            <Button
              size="small"
              variant="contained"
              startIcon={<CloudUpload />}
              onClick={startDeploy}
              disabled={!form.host || !form.user || (!opts.ftp_password && !form.password)}
            >
              {t("projects.app.deploy.deploy", "Deploy now")}
            </Button>
          )}
        </Stack>

        <Divider />
        <Box>
          <Typography variant="caption" color="text.secondary">
            {t("projects.app.deploy.log", "Activity log")}
          </Typography>
          <LogBox elevation={0}>
            {log.length === 0 ? (
              <Typography variant="caption" color="text.disabled">
                {t("projects.app.deploy.noLog", "Hit Test connection or Deploy to see activity here.")}
              </Typography>
            ) : log.map((line, i) => (
              <div key={i}>
                <span style={{ opacity: 0.55 }}>{line.ts} </span>
                <span style={{
                  color: line.type === "error" ? "#e57373" :
                         line.type === "ok" ? "#81c784" :
                         line.type === "upload" ? "#90caf9" : undefined
                }}>{line.text}</span>
              </div>
            ))}
          </LogBox>
        </Box>
      </Pane>
    </Box>
  );
}
