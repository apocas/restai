import { useState, useEffect } from "react";
import {
  Alert, Box, Button, Card, Chip, Dialog, DialogActions, DialogContent, DialogTitle,
  FormControlLabel, Grid, IconButton, InputAdornment, MenuItem, Switch,
  TextField, Tooltip, Typography, styled, CircularProgress,
} from "@mui/material";
import {
  Add, Code, ContentCopy, Delete, Edit, Refresh, VpnKey, PowerSettingsNew, Visibility,
  Lock, LockOpen, ExpandMore, ExpandLess,
} from "@mui/icons-material";
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
}));

const DEFAULT_CONFIG = {
  title: "AI Assistant",
  subtitle: "Ask me anything",
  primaryColor: "#6366f1",
  textColor: "#ffffff",
  position: "right",
  welcomeMessage: "",
  avatarUrl: "",
  stream: false,
};

function WidgetConfigFields({ config, setConfig, compact }) {
  const sm = compact ? 6 : 4;
  return (
    <>
      <Grid item xs={12} sm={sm}>
        <TextField fullWidth size="small" label="Title"
          value={config.title || ""}
          onChange={(e) => setConfig({ ...config, title: e.target.value })}
        />
      </Grid>
      <Grid item xs={12} sm={sm}>
        <TextField fullWidth size="small" label="Subtitle"
          value={config.subtitle || ""}
          onChange={(e) => setConfig({ ...config, subtitle: e.target.value })}
        />
      </Grid>
      <Grid item xs={12} sm={sm}>
        <TextField fullWidth size="small" label="Primary Color"
          value={config.primaryColor || "#6366f1"}
          onChange={(e) => setConfig({ ...config, primaryColor: e.target.value })}
          InputProps={{
            endAdornment: (
              <InputAdornment position="end">
                <input type="color" value={config.primaryColor || "#6366f1"}
                  onChange={(e) => setConfig({ ...config, primaryColor: e.target.value })}
                  style={{ width: 28, height: 28, padding: 0, border: "none", cursor: "pointer", background: "none" }}
                />
              </InputAdornment>
            ),
          }}
        />
      </Grid>
      <Grid item xs={12} sm={sm}>
        <TextField fullWidth select size="small" label="Position"
          value={config.position || "right"}
          onChange={(e) => setConfig({ ...config, position: e.target.value })}
        >
          <MenuItem value="right">Bottom Right</MenuItem>
          <MenuItem value="left">Bottom Left</MenuItem>
        </TextField>
      </Grid>
      <Grid item xs={12}>
        <TextField fullWidth size="small" label="Welcome Message"
          value={config.welcomeMessage || ""}
          onChange={(e) => setConfig({ ...config, welcomeMessage: e.target.value })}
          placeholder="Hi! How can I help you today?"
          helperText="First message shown from the bot when chat opens"
        />
      </Grid>
      <Grid item xs={12}>
        <TextField fullWidth size="small" label="Avatar URL"
          value={config.avatarUrl || ""}
          onChange={(e) => setConfig({ ...config, avatarUrl: e.target.value })}
          placeholder="https://example.com/bot-avatar.png"
          helperText="Custom bot avatar (leave empty for default)"
        />
      </Grid>
      <Grid item xs={12} sm={6}>
        <FormControlLabel
          control={<Switch checked={config.stream || false} onChange={(e) => setConfig({ ...config, stream: e.target.checked })} />}
          label="Enable streaming"
        />
      </Grid>
    </>
  );
}

export default function ProjectWidget({ project }) {
  const auth = useAuth();
  const [widgets, setWidgets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [editWidget, setEditWidget] = useState(null);
  const [newKey, setNewKey] = useState(null);
  const [previewWidget, setPreviewWidget] = useState(null);
  const [previewKey, setPreviewKey] = useState(0);

  const [form, setForm] = useState({ name: "Chat Widget", config: { ...DEFAULT_CONFIG }, allowed_domains: "" });
  const [debouncedFormConfig, setDebouncedFormConfig] = useState(form.config);

  const fetchWidgets = () => {
    api.get(`/projects/${project.id}/widgets`, auth.user.token)
      .then((d) => setWidgets(d.widgets || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (project.id) fetchWidgets();
  }, [project.id]);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedFormConfig(form.config), 600);
    return () => clearTimeout(timer);
  }, [form.config]);

  const handleCreate = () => {
    setCreating(true);
    const domains = form.allowed_domains
      ? form.allowed_domains.split(",").map((d) => d.trim()).filter(Boolean)
      : [];
    api.post(`/projects/${project.id}/widgets`, { name: form.name, config: form.config, allowed_domains: domains }, auth.user.token)
      .then((d) => {
        setNewKey(d.widget_key);
        setPreviewWidget({ ...d, widget_key: d.widget_key });
        setForm({ name: "Chat Widget", config: { ...DEFAULT_CONFIG }, allowed_domains: "" });
        fetchWidgets();
        toast.success("Widget created");
      })
      .catch(() => {})
      .finally(() => setCreating(false));
  };

  const handleToggle = (widget) => {
    api.patch(`/projects/${project.id}/widgets/${widget.id}`, { enabled: !widget.enabled }, auth.user.token)
      .then(() => fetchWidgets())
      .catch(() => {});
  };

  const handleDelete = (widget) => {
    if (!window.confirm(`Delete widget "${widget.name}"?`)) return;
    api.delete(`/projects/${project.id}/widgets/${widget.id}`, auth.user.token)
      .then(() => {
        fetchWidgets();
        if (previewWidget?.id === widget.id) setPreviewWidget(null);
        toast.success("Widget deleted");
      })
      .catch(() => {});
  };

  const handleRegenerateKey = (widget) => {
    if (!window.confirm("Regenerate key? The old key will stop working immediately.")) return;
    api.post(`/projects/${project.id}/widgets/${widget.id}/regenerate-key`, {}, auth.user.token)
      .then((d) => {
        setNewKey(d.widget_key);
        setPreviewWidget({ ...d, widget_key: d.widget_key });
        toast.success("Key regenerated");
      })
      .catch(() => {});
  };

  const handleSaveEdit = () => {
    if (!editWidget) return;
    const domains = editWidget.allowed_domains_str
      ? editWidget.allowed_domains_str.split(",").map((d) => d.trim()).filter(Boolean)
      : [];
    api.patch(`/projects/${project.id}/widgets/${editWidget.id}`, {
      name: editWidget.name,
      config: editWidget.config,
      allowed_domains: domains,
    }, auth.user.token)
      .then(() => { fetchWidgets(); setEditWidget(null); toast.success("Widget updated"); })
      .catch(() => {});
  };

  const [contextSecret, setContextSecret] = useState(null);
  const [showTutorial, setShowTutorial] = useState(false);

  const handleGenerateContextSecret = (widget) => {
    api.post(`/projects/${project.id}/widgets/${widget.id}/context-secret`, {}, auth.user.token)
      .then((d) => {
        setContextSecret({ widgetId: widget.id, secret: d.context_secret });
        fetchWidgets();
        toast.success("Context secret generated");
      })
      .catch(() => {});
  };

  const handleRemoveContextSecret = (widget) => {
    if (!window.confirm("Remove context secret? Signed context tokens will no longer be accepted.")) return;
    api.delete(`/projects/${project.id}/widgets/${widget.id}/context-secret`, auth.user.token)
      .then(() => {
        fetchWidgets();
        toast.success("Context secret removed");
      })
      .catch(() => {});
  };

  const serverUrl = process.env.REACT_APP_RESTAI_API_URL || window.location.origin;

  const getEmbedCode = (widget) => {
    const key = widget.widget_key || widget.key_prefix + "...";
    return `<script\n  src="${serverUrl}/widget/chat.js"\n  data-widget-key="${key}"\n  data-server="${serverUrl}"\n></script>`;
  };

  const copyEmbedCode = (widget) => {
    navigator.clipboard.writeText(getEmbedCode(widget));
    toast.success("Embed code copied");
  };

  const getPreviewHtml = (widget) => {
    const key = widget.widget_key || "";
    const cfg = widget.config || {};
    return `<!DOCTYPE html>
<html><head><style>body{margin:0;padding:0;height:100%;background:#f5f5f5;font-family:sans-serif;display:flex;align-items:center;justify-content:center;color:#888;font-size:14px}</style></head>
<body><p>Widget preview</p>
<script src="${serverUrl}/widget/chat.js"
  data-widget-key="${key}"
  data-server="${serverUrl}"
  data-title="${cfg.title || "AI Assistant"}"
  data-subtitle="${cfg.subtitle || "Ask me anything"}"
  data-primary-color="${cfg.primaryColor || "#6366f1"}"
  data-text-color="${cfg.textColor || "#ffffff"}"
  data-position="${cfg.position || "right"}"
  ${cfg.stream ? 'data-stream="true"' : ""}
  ${cfg.welcomeMessage ? `data-welcome-message="${cfg.welcomeMessage}"` : ""}
  ${cfg.avatarUrl ? `data-avatar-url="${cfg.avatarUrl}"` : ""}
></script></body></html>`;
  };

  if (loading) return <Box sx={{ textAlign: "center", py: 4 }}><CircularProgress /></Box>;

  return (
    <Grid container spacing={3}>
      {/* Context secret shown once alert */}
      {contextSecret && (
        <Grid item xs={12}>
          <Alert
            severity="info"
            action={
              <Button color="inherit" size="small" onClick={() => {
                navigator.clipboard.writeText(contextSecret.secret);
                toast.success("Context secret copied");
              }}>
                Copy Secret
              </Button>
            }
            onClose={() => setContextSecret(null)}
          >
            <Typography variant="subtitle2" gutterBottom>Context Secret (shown only once)</Typography>
            <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
              {contextSecret.secret}
            </Typography>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              Use this secret in your backend to sign JWT tokens for widget context injection.
            </Typography>
          </Alert>
        </Grid>
      )}

      {/* Key shown once alert */}
      {newKey && (
        <Grid item xs={12}>
          <Alert
            severity="warning"
            action={
              <Button color="inherit" size="small" onClick={() => {
                navigator.clipboard.writeText(newKey);
                toast.success("Widget key copied");
              }}>
                Copy Key
              </Button>
            }
            onClose={() => setNewKey(null)}
          >
            <Typography variant="subtitle2" gutterBottom>Widget Key (shown only once)</Typography>
            <Typography variant="body2" sx={{ fontFamily: "monospace", wordBreak: "break-all" }}>
              {newKey}
            </Typography>
          </Alert>
        </Grid>
      )}

      {/* Widget List + Preview side by side */}
      <Grid item xs={12} md={previewWidget ? 6 : 12}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <SectionTitle><Code fontSize="small" /> Widgets</SectionTitle>

          {widgets.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 2 }}>
              No widgets yet.
            </Typography>
          ) : (
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              {widgets.map((w) => (
                <Card key={w.id} variant="outlined" sx={{ p: 2, display: "flex", alignItems: "center", gap: 2, flexWrap: "wrap" }}>
                  <Box sx={{ flex: 1, minWidth: 150 }}>
                    <Typography variant="subtitle2">{w.name}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {w.key_prefix}... &middot; {(w.allowed_domains || []).length > 0 ? `${w.allowed_domains.length} domain(s)` : "All domains"}
                    </Typography>
                  </Box>
                  <Box sx={{ display: "flex", gap: 0.5, alignItems: "center" }}>
                    <Chip
                      label={w.enabled ? "Active" : "Disabled"}
                      size="small"
                      color={w.enabled ? "success" : "default"}
                      variant="outlined"
                    />
                    {w.has_context_secret && (
                      <Chip label="Context" size="small" icon={<Lock sx={{ fontSize: 14 }} />} color="info" variant="outlined" />
                    )}
                  </Box>
                  <Box sx={{ display: "flex", gap: 0.5 }}>
                    <Tooltip title={w.enabled ? "Disable" : "Enable"}>
                      <IconButton size="small" onClick={() => handleToggle(w)}>
                        <PowerSettingsNew fontSize="small" color={w.enabled ? "success" : "disabled"} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Preview">
                      <IconButton size="small" onClick={() => { setPreviewWidget(w); setPreviewKey((k) => k + 1); }}>
                        <Visibility fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Edit">
                      <IconButton size="small" onClick={() => setEditWidget({
                        ...w,
                        config: w.config || { ...DEFAULT_CONFIG },
                        allowed_domains_str: (w.allowed_domains || []).join(", "),
                      })}>
                        <Edit fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={w.has_context_secret ? "Regenerate Context Secret" : "Generate Context Secret"}>
                      <IconButton size="small" onClick={() => handleGenerateContextSecret(w)}>
                        <Lock fontSize="small" color={w.has_context_secret ? "info" : "disabled"} />
                      </IconButton>
                    </Tooltip>
                    {w.has_context_secret && (
                      <Tooltip title="Remove Context Secret">
                        <IconButton size="small" onClick={() => handleRemoveContextSecret(w)}>
                          <LockOpen fontSize="small" color="warning" />
                        </IconButton>
                      </Tooltip>
                    )}
                    <Tooltip title="Regenerate Key">
                      <IconButton size="small" onClick={() => handleRegenerateKey(w)}>
                        <VpnKey fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title="Delete">
                      <IconButton size="small" color="error" onClick={() => handleDelete(w)}>
                        <Delete fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </Box>
                </Card>
              ))}
            </Box>
          )}
        </Card>
      </Grid>

      {/* Live Preview */}
      {previewWidget && (
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
            <Box sx={{ borderRadius: 2, overflow: "hidden", border: "1px solid #eee", height: 400 }}>
              <iframe
                key={previewKey}
                title="Widget Preview"
                srcDoc={getPreviewHtml(previewWidget)}
                style={{ width: "100%", height: "100%", border: "none" }}
                sandbox="allow-scripts allow-same-origin"
              />
            </Box>
            <Box sx={{ mt: 2, display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 1 }}>
              <CodeBlock sx={{ flex: 1, fontSize: "0.72rem" }}>{getEmbedCode(previewWidget)}</CodeBlock>
              <Tooltip title="Copy embed code">
                <IconButton size="small" onClick={() => copyEmbedCode(previewWidget)} sx={{ mt: 0.5 }}>
                  <ContentCopy fontSize="small" />
                </IconButton>
              </Tooltip>
            </Box>
          </Card>
        </Grid>
      )}

      {/* Create Widget — form + live preview */}
      <Grid item xs={12} md={6}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <SectionTitle><Add fontSize="small" /> Create Widget</SectionTitle>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Widget Name"
                value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Allowed Domains"
                value={form.allowed_domains}
                onChange={(e) => setForm({ ...form, allowed_domains: e.target.value })}
                placeholder="example.com, *.mysite.com"
                helperText="Comma-separated. Leave empty to allow all domains."
              />
            </Grid>
            <WidgetConfigFields
              config={form.config}
              setConfig={(c) => setForm({ ...form, config: c })}
            />
            <Grid item xs={12}>
              <Button variant="contained" onClick={handleCreate} disabled={creating || !form.name.trim()}>
                {creating ? <CircularProgress size={20} /> : "Create Widget"}
              </Button>
            </Grid>
          </Grid>
        </Card>
      </Grid>
      <Grid item xs={12} md={6}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", mb: 1.5 }}>
            <SectionTitle sx={{ mb: 0 }}>Preview</SectionTitle>
            <Tooltip title="Reload preview">
              <IconButton size="small" onClick={() => setPreviewKey((k) => k + 1)}>
                <Refresh fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
          <Box sx={{ borderRadius: 2, overflow: "hidden", border: "1px solid #eee", height: 480 }}>
            <iframe
              key={`create-${previewKey}-${JSON.stringify(debouncedFormConfig)}`}
              title="Create Widget Preview"
              srcDoc={getPreviewHtml({ config: debouncedFormConfig })}
              style={{ width: "100%", height: "100%", border: "none" }}
              sandbox="allow-scripts allow-same-origin"
            />
          </Box>
        </Card>
      </Grid>

      {/* Context Injection Tutorial */}
      <Grid item xs={12}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <Box
            sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer" }}
            onClick={() => setShowTutorial(!showTutorial)}
          >
            <SectionTitle sx={{ mb: 0 }}><Lock fontSize="small" /> Site Context Injection</SectionTitle>
            <IconButton size="small">{showTutorial ? <ExpandLess /> : <ExpandMore />}</IconButton>
          </Box>

          {showTutorial && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Pass information about your logged-in users (name, role, preferences) to the AI project so it can personalize responses.
                Context is signed with a secret key to prevent tampering.
              </Typography>

              <Typography variant="subtitle2" sx={{ mb: 1 }}>1. Generate a Context Secret</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Click the <Lock sx={{ fontSize: 14, verticalAlign: "middle" }} /> button on your widget above. Save the secret securely in your backend environment variables.
              </Typography>

              <Typography variant="subtitle2" sx={{ mb: 1 }}>2. Sign a JWT on your backend</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Use any JWT library to create a signed token with your user's information. Always include an <code>exp</code> (expiry) claim.
              </Typography>

              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5, fontWeight: 600 }}>Python</Typography>
              <CodeBlock sx={{ mb: 2, fontSize: "0.75rem" }}>{`import jwt, time

token = jwt.encode({
    "sub": user.id,
    "name": user.name,
    "role": user.role,
    "email": user.email,
    "meta": {"plan": "enterprise", "department": "engineering"},
    "exp": int(time.time()) + 3600  # 1 hour
}, CONTEXT_SECRET, algorithm="HS256")`}</CodeBlock>

              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5, fontWeight: 600 }}>Node.js</Typography>
              <CodeBlock sx={{ mb: 2, fontSize: "0.75rem" }}>{`const jwt = require('jsonwebtoken');

const token = jwt.sign({
    sub: user.id,
    name: user.name,
    role: user.role,
    email: user.email,
    meta: { plan: "enterprise", department: "engineering" }
}, CONTEXT_SECRET, { expiresIn: '1h' });`}</CodeBlock>

              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5, fontWeight: 600 }}>PHP</Typography>
              <CodeBlock sx={{ mb: 2, fontSize: "0.75rem" }}>{`use Firebase\\JWT\\JWT;

$token = JWT::encode([
    'sub' => $user->id,
    'name' => $user->name,
    'role' => $user->role,
    'email' => $user->email,
    'meta' => ['plan' => 'enterprise', 'department' => 'engineering'],
    'exp' => time() + 3600
], $contextSecret, 'HS256');`}</CodeBlock>

              <Typography variant="subtitle2" sx={{ mb: 1 }}>3. Render the widget with the token</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                Pass the signed token via the <code>data-context-token</code> attribute. Generate a fresh token on each page load.
              </Typography>
              <CodeBlock sx={{ mb: 2, fontSize: "0.75rem" }}>{`<script
  src="${serverUrl}/widget/chat.js"
  data-widget-key="wk_your_widget_key"
  data-server="${serverUrl}"
  data-context-token="<?= $token ?>"
></script>`}</CodeBlock>

              <Typography variant="subtitle2" sx={{ mb: 1 }}>4. Use context in your system prompt</Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                The context is automatically prepended to the system prompt as a <code>[User Context]</code> block.
                You can also use template variables for precise control:
              </Typography>
              <CodeBlock sx={{ mb: 2, fontSize: "0.75rem" }}>{`You are a helpful assistant for {{context.name}}.
They are on the {{context.meta.plan}} plan with {{context.role}} access.
Adjust your responses accordingly.`}</CodeBlock>

              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                Template variables use the format <code>{"{{context.key}}"}</code>. Nested values use dots: <code>{"{{context.meta.plan}}"}</code>.
                Missing keys resolve to empty strings, so the same prompt works with or without context.
              </Typography>
            </Box>
          )}
        </Card>
      </Grid>

      {/* Edit Dialog */}
      {editWidget && (
        <Dialog open onClose={() => setEditWidget(null)} maxWidth="sm" fullWidth>
          <DialogTitle>Edit Widget</DialogTitle>
          <DialogContent>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid item xs={12}>
                <TextField fullWidth size="small" label="Name"
                  value={editWidget.name}
                  onChange={(e) => setEditWidget({ ...editWidget, name: e.target.value })}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField fullWidth size="small" label="Allowed Domains"
                  value={editWidget.allowed_domains_str}
                  onChange={(e) => setEditWidget({ ...editWidget, allowed_domains_str: e.target.value })}
                  placeholder="example.com, *.mysite.com"
                  helperText="Comma-separated. Leave empty to allow all."
                />
              </Grid>
              <WidgetConfigFields
                config={editWidget.config}
                setConfig={(c) => setEditWidget({ ...editWidget, config: c })}
                compact
              />
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditWidget(null)}>Cancel</Button>
            <Button variant="contained" onClick={handleSaveEdit}>Save</Button>
          </DialogActions>
        </Dialog>
      )}
    </Grid>
  );
}
