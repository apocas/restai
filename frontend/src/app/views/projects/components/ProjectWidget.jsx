import { useState, useEffect, useRef } from "react";
import {
  Box, Button, Card, Grid, IconButton, InputAdornment, Switch, FormControlLabel,
  MenuItem, TextField, Tooltip, Typography, styled, CircularProgress,
} from "@mui/material";
import { ContentCopy, Code, Refresh } from "@mui/icons-material";
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

  const [config, setConfig] = useState({
    title: "AI Assistant",
    subtitle: "Ask me anything",
    primaryColor: "#6366f1",
    textColor: "#ffffff",
    position: "right",
    welcomeMessage: "",
    avatarUrl: "",
    stream: false,
  });

  const [widgetKey, setWidgetKey] = useState(null); // full API key string
  const [loading, setLoading] = useState(true);
  const [previewKey, setPreviewKey] = useState(0);

  useEffect(() => {
    if (!auth.user?.username || !project.id) return;

    // Check if a widget key already exists for this project
    api.get(`/users/${auth.user.username}/apikeys`, auth.user.token)
      .then((keys) => {
        const existing = keys.find(
          (k) => k.description === `widget-project-${project.id}` && k.read_only &&
                 k.allowed_projects && k.allowed_projects.length === 1 && k.allowed_projects[0] === project.id
        );
        if (existing) {
          // Key exists but we don't have the full key — need to create a new one
          // The full key is only available at creation time
          setWidgetKey(null);
        }
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [auth.user?.username, project.id]);

  const generateKey = () => {
    setLoading(true);
    api.post(
      `/users/${auth.user.username}/apikeys`,
      {
        description: `widget-project-${project.id}`,
        allowed_projects: [project.id],
        read_only: true,
      },
      auth.user.token,
    )
      .then((data) => {
        setWidgetKey(data.api_key);
        toast.success("Widget API key created");
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const serverUrl = process.env.REACT_APP_RESTAI_API_URL || window.location.origin;

  const embedCode = widgetKey
    ? `<script
  src="${serverUrl}/widget/chat.js"
  data-project-id="${project.id}"
  data-api-key="${widgetKey}"
  data-title="${config.title}"
  data-subtitle="${config.subtitle}"
  data-primary-color="${config.primaryColor}"
  data-text-color="${config.textColor}"
  data-position="${config.position}"${config.stream ? `\n  data-stream="true"` : ""}${config.welcomeMessage ? `\n  data-welcome-message="${config.welcomeMessage}"` : ""}${config.avatarUrl ? `\n  data-avatar-url="${config.avatarUrl}"` : ""}
></script>`
    : null;

  const copyCode = () => {
    if (embedCode) {
      navigator.clipboard.writeText(embedCode);
      toast.success("Embed code copied");
    }
  };

  const previewHtml = widgetKey
    ? `<!DOCTYPE html>
<html><head><style>body{margin:0;padding:0;height:100%;background:#f5f5f5;font-family:sans-serif;display:flex;align-items:center;justify-content:center;color:#888;font-size:14px}</style></head>
<body><p>Widget preview</p>
<script src="${serverUrl}/widget/chat.js"
  data-project-id="${project.id}"
  data-api-key="${widgetKey}"
  data-title="${config.title}"
  data-subtitle="${config.subtitle}"
  data-primary-color="${config.primaryColor}"
  data-text-color="${config.textColor}"
  data-position="${config.position}"
  ${config.stream ? `data-stream="true"` : ""}
  ${config.welcomeMessage ? `data-welcome-message="${config.welcomeMessage}"` : ""}
  ${config.avatarUrl ? `data-avatar-url="${config.avatarUrl}"` : ""}
  data-server="${serverUrl}"
></script></body></html>`
    : null;

  return (
    <Grid container spacing={3}>
      {/* Configuration */}
      <Grid item xs={12} md={6}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <SectionTitle><Code fontSize="small" /> Widget Configuration</SectionTitle>

          {!widgetKey && (
            <Box sx={{ textAlign: "center", py: 3, mb: 2 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Generate a dedicated read-only API key for this widget. The key will be scoped to this project only.
              </Typography>
              <Button variant="contained" onClick={generateKey} disabled={loading}>
                {loading ? <CircularProgress size={20} /> : "Generate Widget Key"}
              </Button>
            </Box>
          )}

          <Grid container spacing={2}>
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

            <Grid item xs={12} sm={6}>
              <FormControlLabel
                control={<Switch checked={config.stream} onChange={(e) => setConfig({ ...config, stream: e.target.checked })} />}
                label="Enable streaming"
              />
              <Typography variant="caption" color="text.secondary" display="block">
                Show responses token by token as they arrive
              </Typography>
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
            <Tooltip title="Copy to clipboard">
              <span>
                <IconButton size="small" onClick={copyCode} disabled={!embedCode}>
                  <ContentCopy fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
          {embedCode ? (
            <CodeBlock>{embedCode}</CodeBlock>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
              Generate a widget key above to see the embed code.
            </Typography>
          )}
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
              <IconButton size="small" onClick={() => setPreviewKey((k) => k + 1)} disabled={!previewHtml}>
                <Refresh fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          {previewHtml ? (
            <Box sx={{ borderRadius: 2, overflow: "hidden", border: "1px solid #eee", height: 480 }}>
              <iframe
                key={previewKey}
                title="Widget Preview"
                srcDoc={previewHtml}
                style={{ width: "100%", height: "100%", border: "none" }}
                sandbox="allow-scripts allow-same-origin"
              />
            </Box>
          ) : (
            <Box sx={{ textAlign: "center", py: 6, color: "text.secondary" }}>
              <Typography variant="body2">Generate a widget key to preview the chat widget.</Typography>
            </Box>
          )}
        </Card>
      </Grid>
    </Grid>
  );
}
