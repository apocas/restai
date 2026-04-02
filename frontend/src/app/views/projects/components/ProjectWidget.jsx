import { useState, useEffect, useRef } from "react";
import {
  Box, Button, Card, Chip, Grid, IconButton, InputAdornment,
  MenuItem, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { ContentCopy, Code, Refresh, Warning } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toast } from "react-toastify";

const SectionTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  fontSize: "0.9rem",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.5),
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1.5),
}));

const CodeBlock = styled(Box)(({ theme }) => ({
  background: "#1e1e2e",
  color: "#cdd6f4",
  padding: theme.spacing(2),
  borderRadius: 8,
  fontFamily: "'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace",
  fontSize: "0.8rem",
  lineHeight: 1.6,
  overflowX: "auto",
  whiteSpace: "pre-wrap",
  wordBreak: "break-all",
  position: "relative",
}));

export default function ProjectWidget({ project }) {
  const auth = useAuth();
  const previewRef = useRef(null);

  const [config, setConfig] = useState({
    title: "AI Assistant",
    subtitle: "Ask me anything",
    primaryColor: "#6366f1",
    textColor: "#ffffff",
    position: "right",
    welcomeMessage: "",
    avatarUrl: "",
  });

  const [apiKeys, setApiKeys] = useState([]);
  const [selectedKey, setSelectedKey] = useState("");
  const [previewKey, setPreviewKey] = useState(0);

  useEffect(() => {
    if (!auth.user?.username) return;
    api.get(`/users/${auth.user.username}/apikeys`, auth.user.token)
      .then(setApiKeys)
      .catch(() => {});
  }, [auth.user?.username]);

  // Validate selected API key
  const selectedKeyObj = apiKeys.find((k) => k.key_prefix === selectedKey) || null;
  const keyErrors = [];
  if (selectedKeyObj) {
    if (!selectedKeyObj.read_only) {
      keyErrors.push("Key must be read-only. Edit the key or create a new read-only key.");
    }
    if (!selectedKeyObj.allowed_projects || !Array.isArray(selectedKeyObj.allowed_projects)) {
      keyErrors.push("Key must be scoped to this project only. It currently has access to all projects.");
    } else if (selectedKeyObj.allowed_projects.length !== 1 || selectedKeyObj.allowed_projects[0] !== project.id) {
      keyErrors.push(`Key must be scoped to only this project (ID ${project.id}). It currently has access to other projects.`);
    }
  }
  const keyValid = selectedKey && keyErrors.length === 0;

  const serverUrl = process.env.REACT_APP_RESTAI_API_URL || window.location.origin;

  const embedCode = `<script
  src="${serverUrl}/widget/chat.js"
  data-project-id="${project.id}"
  data-api-key="${selectedKey || "YOUR_API_KEY"}"
  data-title="${config.title}"
  data-subtitle="${config.subtitle}"
  data-primary-color="${config.primaryColor}"
  data-text-color="${config.textColor}"
  data-position="${config.position}"${config.welcomeMessage ? `\n  data-welcome-message="${config.welcomeMessage}"` : ""}${config.avatarUrl ? `\n  data-avatar-url="${config.avatarUrl}"` : ""}
></script>`;

  const copyCode = () => {
    navigator.clipboard.writeText(embedCode);
    toast.success("Embed code copied");
  };

  // Build preview HTML
  const previewHtml = `<!DOCTYPE html>
<html><head><style>body{margin:0;padding:0;height:100%;background:#f5f5f5;font-family:sans-serif;display:flex;align-items:center;justify-content:center;color:#888;font-size:14px}</style></head>
<body><p>Widget preview</p>
<script src="${serverUrl}/widget/chat.js"
  data-project-id="${project.id}"
  data-api-key="${selectedKey || ""}"
  data-title="${config.title}"
  data-subtitle="${config.subtitle}"
  data-primary-color="${config.primaryColor}"
  data-text-color="${config.textColor}"
  data-position="${config.position}"
  ${config.welcomeMessage ? `data-welcome-message="${config.welcomeMessage}"` : ""}
  ${config.avatarUrl ? `data-avatar-url="${config.avatarUrl}"` : ""}
  data-server="${serverUrl}"
></script></body></html>`;

  return (
    <Grid container spacing={3}>
      {/* Configuration */}
      <Grid item xs={12} md={6}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <SectionTitle><Code fontSize="small" /> Widget Configuration</SectionTitle>

          <Grid container spacing={2}>
            <Grid item xs={12}>
              <TextField
                fullWidth select size="small" label="API Key"
                value={selectedKey}
                onChange={(e) => setSelectedKey(e.target.value)}
                error={selectedKey !== "" && keyErrors.length > 0}
                helperText={
                  selectedKey && keyErrors.length > 0
                    ? keyErrors[0]
                    : "Must be a read-only key scoped to this project only"
                }
              >
                <MenuItem value="">Select an API key...</MenuItem>
                {apiKeys.map((k) => (
                  <MenuItem key={k.id} value={k.key_prefix}>
                    {k.description || k.key_prefix}
                    {k.read_only ? " (read-only)" : " (read-write)"}
                    {k.allowed_projects && k.allowed_projects.length === 1 && k.allowed_projects[0] === project.id ? " (this project)" : ""}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Title"
                value={config.title}
                onChange={(e) => setConfig({ ...config, title: e.target.value })}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Subtitle"
                value={config.subtitle}
                onChange={(e) => setConfig({ ...config, subtitle: e.target.value })}
              />
            </Grid>

            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Primary Color"
                value={config.primaryColor}
                onChange={(e) => setConfig({ ...config, primaryColor: e.target.value })}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <input type="color" value={config.primaryColor}
                        onChange={(e) => setConfig({ ...config, primaryColor: e.target.value })}
                        style={{ width: 28, height: 28, padding: 0, border: "none", cursor: "pointer", background: "none" }}
                      />
                    </InputAdornment>
                  ),
                }}
              />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth select size="small" label="Position"
                value={config.position}
                onChange={(e) => setConfig({ ...config, position: e.target.value })}
              >
                <MenuItem value="right">Bottom Right</MenuItem>
                <MenuItem value="left">Bottom Left</MenuItem>
              </TextField>
            </Grid>

            <Grid item xs={12}>
              <TextField fullWidth size="small" label="Welcome Message"
                value={config.welcomeMessage}
                onChange={(e) => setConfig({ ...config, welcomeMessage: e.target.value })}
                placeholder="Hi! How can I help you today?"
                helperText="First message shown from the bot when chat opens"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth size="small" label="Avatar URL"
                value={config.avatarUrl}
                onChange={(e) => setConfig({ ...config, avatarUrl: e.target.value })}
                placeholder="https://example.com/bot-avatar.png"
                helperText="Custom bot avatar (leave empty for default)"
              />
            </Grid>
          </Grid>
        </Card>

        {/* Embed Code */}
        <Card elevation={1} sx={{ p: 2.5, mt: 2 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1 }}>
            <SectionTitle sx={{ mb: 0 }}>Embed Code</SectionTitle>
            <Tooltip title={keyValid ? "Copy to clipboard" : "Fix API key issues first"}>
              <span>
                <IconButton size="small" onClick={copyCode} disabled={!keyValid}>
                  <ContentCopy fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
          <CodeBlock>{embedCode}</CodeBlock>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
            Paste this script tag into your website's HTML, before the closing <code>&lt;/body&gt;</code> tag.
          </Typography>
        </Card>
      </Grid>

      {/* Live Preview */}
      <Grid item xs={12} md={6}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
            <SectionTitle sx={{ mb: 0 }}>Live Preview</SectionTitle>
            <Tooltip title="Reload preview">
              <IconButton size="small" onClick={() => setPreviewKey((k) => k + 1)}>
                <Refresh fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          {!keyValid ? (
            <Box sx={{ textAlign: "center", py: 6, color: "text.secondary" }}>
              {selectedKey && keyErrors.length > 0 ? (
                <>
                  <Warning color="error" sx={{ fontSize: 40, mb: 1 }} />
                  <Typography variant="body2" color="error.main">API key does not meet widget requirements:</Typography>
                  {keyErrors.map((err, i) => (
                    <Typography key={i} variant="caption" display="block" color="error.main" sx={{ mt: 0.5 }}>{err}</Typography>
                  ))}
                </>
              ) : (
                <>
                  <Typography variant="body2">Select a valid API key to preview the widget.</Typography>
                  <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                    Create a read-only, project-scoped API key in your user profile.
                  </Typography>
                </>
              )}
            </Box>
          ) : (
            <Box sx={{ borderRadius: 2, overflow: "hidden", border: "1px solid #eee", height: 480 }}>
              <iframe
                key={previewKey}
                title="Widget Preview"
                srcDoc={previewHtml}
                style={{ width: "100%", height: "100%", border: "none" }}
                sandbox="allow-scripts allow-same-origin"
              />
            </Box>
          )}
        </Card>
      </Grid>
    </Grid>
  );
}
