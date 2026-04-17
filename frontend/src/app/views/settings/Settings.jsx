import { useState, useEffect } from "react";
import {
  Grid, styled, Box, Card, Divider, TextField, Button,
  Switch, FormControlLabel, FormHelperText, Typography, Select, MenuItem, InputLabel, FormControl,
  Collapse, IconButton
} from "@mui/material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { toast } from "react-toastify";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";
import { Settings as SettingsIcon, Storage, Security, ExpandMore, ExpandLess } from "@mui/icons-material";
import { H4 } from "app/components/Typography";
import ProjectTabNav from "app/views/projects/components/ProjectTabNav";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

const TABS = [
  { name: "General", Icon: SettingsIcon },
  { name: "Authentication", Icon: Security },
];

export default function SettingsPage() {
  const auth = useAuth();
  const { refreshCapabilities } = usePlatformCapabilities();
  const [active, setActive] = useState("General");

  const [form, setForm] = useState({
    app_name: "RESTai",
    hide_branding: false,
    proxy_enabled: false,
    proxy_url: "",
    proxy_key: "",
    proxy_team_id: "",
    max_audio_upload_size: 10,
    data_retention_days: 0,
    currency: "EUR",
    redis_host: "",
    redis_port: "6379",
    redis_password: "",
    redis_database: "0",
    auth_disable_local: false,
    sso_auto_create_user: false,
    sso_allowed_domains: "*",
    sso_google_client_id: "",
    sso_google_client_secret: "",
    sso_google_redirect_uri: "",
    sso_google_scope: "openid email profile",
    sso_microsoft_client_id: "",
    sso_microsoft_client_secret: "",
    sso_microsoft_tenant_id: "",
    sso_microsoft_redirect_uri: "",
    sso_microsoft_scope: "openid email profile",
    sso_github_client_id: "",
    sso_github_client_secret: "",
    sso_github_redirect_uri: "",
    sso_github_scope: "user:email",
    sso_oidc_client_id: "",
    sso_oidc_client_secret: "",
    sso_oidc_provider_url: "",
    sso_oidc_redirect_uri: "",
    sso_oidc_scopes: "openid email profile",
    sso_oidc_provider_name: "SSO",
    sso_auto_restricted: true,
    sso_auto_team_id: "",
    sso_oidc_email_claim: "email",
    mcp_enabled: false,
    docker_enabled: false,
    docker_url: "",
    docker_image: "python:3.12-slim",
    docker_timeout: 900,
    docker_network: "none",
    docker_read_only: true,
    system_llm: "",
    enforce_2fa: false,
  });
  const [teams, setTeams] = useState([]);
  const [llms, setLlms] = useState([]);
  const [saving, setSaving] = useState(false);
  const [dockerTest, setDockerTest] = useState(null); // null | "testing" | {status, detail}
  const [telemetryEnabled, setTelemetryEnabled] = useState(null);
  const [expanded, setExpanded] = useState({ google: false, microsoft: false, github: false, oidc: false });

  const toggleExpanded = (section) => () => {
    setExpanded((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const fetchSettings = () => {
    api.get("/settings", auth.user.token)
      .then((data) => setForm(data))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = "RESTai - Settings";
    fetchSettings();
    api.get("/teams", auth.user.token).then((d) => setTeams(d.teams || [])).catch(() => {});
    api.get("/llms", auth.user.token).then((d) => setLlms(Array.isArray(d) ? d : (d?.llms || []))).catch(() => {});
    api.get("/version", auth.user.token, { silent: true }).then((d) => { if (d) setTelemetryEnabled(d.telemetry); }).catch(() => {});
  }, []);

  const handleChange = (field) => (e) => {
    const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = () => {
    setSaving(true);
    const body = { ...form };
    body.max_audio_upload_size = parseInt(body.max_audio_upload_size, 10) || 10;
    body.data_retention_days = parseInt(body.data_retention_days, 10) || 0;
    body.docker_timeout = parseInt(body.docker_timeout, 10) || 900;

    api.patch("/settings", body, auth.user.token)
      .then((data) => {
        setForm(data);
        toast.success("Settings saved");
        refreshCapabilities();
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  const CollapsibleCardHeader = ({ icon: Icon, title, section }) => (
    <FlexBox sx={{ cursor: "pointer" }} onClick={toggleExpanded(section)}>
      <Icon sx={{ ml: 2 }} />
      <H4 sx={{ p: 2, flex: 1 }}>{title}</H4>
      <IconButton size="small" sx={{ mr: 2 }}>
        {expanded[section] ? <ExpandLess /> : <ExpandMore />}
      </IconButton>
    </FlexBox>
  );

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Settings", path: "/settings" }]} />
      </Box>

      <Grid container spacing={3}>
        <Grid item md={2} xs={12}>
          <ProjectTabNav tabs={TABS} active={active} setActive={setActive} />
        </Grid>

        <Grid item md={10} xs={12}>
          {/* ===== GENERAL TAB ===== */}
          {active === "General" && (
            <Grid container spacing={3}>
              {/* App */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Platform</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="App Name" value={form.app_name} onChange={handleChange("app_name")} />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <FormControlLabel
                        control={<Switch checked={form.hide_branding} onChange={handleChange("hide_branding")} />}
                        label="Hide Branding"
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <FormControl fullWidth>
                        <InputLabel>Currency</InputLabel>
                        <Select value={form.currency} label="Currency" onChange={handleChange("currency")}>
                          <MenuItem value="USD">USD ($)</MenuItem>
                          <MenuItem value="EUR">EUR (&euro;)</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <FormControl fullWidth>
                        <InputLabel>System LLM</InputLabel>
                        <Select
                          value={form.system_llm ?? ""}
                          label="System LLM"
                          onChange={handleChange("system_llm")}
                        >
                          <MenuItem value=""><em>None</em></MenuItem>
                          {llms.map((l) => (
                            <MenuItem key={l.id || l.name} value={l.name}>{l.name}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                        LLM used by the platform for internal tasks (prompt helpers, summarization, etc). Leave empty to disable.
                      </Typography>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* LLM Proxy */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>LLM Proxy</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={form.proxy_enabled} onChange={handleChange("proxy_enabled")} />}
                        label="Enable Proxy"
                      />
                    </Grid>
                    {form.proxy_enabled && (
                      <>
                        <Grid item xs={12} md={4}>
                          <TextField fullWidth label="Proxy URL" value={form.proxy_url} onChange={handleChange("proxy_url")} />
                        </Grid>
                        <Grid item xs={12} md={4}>
                          <TextField fullWidth label="Proxy Key" type="password" value={form.proxy_key} onChange={handleChange("proxy_key")} />
                        </Grid>
                        <Grid item xs={12} md={4}>
                          <TextField fullWidth label="Proxy Team ID" value={form.proxy_team_id} onChange={handleChange("proxy_team_id")} />
                        </Grid>
                      </>
                    )}
                  </Grid>
                </Card>
              </Grid>

              {/* Limits */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Limits</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="Max Audio Upload Size (MB)" type="number" inputProps={{ min: 1 }}
                        value={form.max_audio_upload_size} onChange={handleChange("max_audio_upload_size")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="Data Retention (days)" type="number" inputProps={{ min: 0 }}
                        value={form.data_retention_days} onChange={handleChange("data_retention_days")}
                        helperText="Auto-delete logs older than this. 0 = keep forever." />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* Redis */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Chat History (Redis)</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="Redis Host" placeholder="Leave empty for in-memory"
                        value={form.redis_host} onChange={handleChange("redis_host")} />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label="Port" value={form.redis_port} onChange={handleChange("redis_port")} />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label="Password" type="password" value={form.redis_password} onChange={handleChange("redis_password")} />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label="Database" value={form.redis_database} onChange={handleChange("redis_database")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* MCP */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>MCP Server</Typography>
                  <FormControlLabel
                    control={<Switch checked={form.mcp_enabled} onChange={handleChange("mcp_enabled")} />}
                    label="Enable MCP Server"
                  />
                  <Typography variant="caption" color="text.secondary" display="block">
                    Expose projects as MCP tools at /mcp/sse. Requires server restart.
                  </Typography>
                </Card>
              </Grid>

              {/* Docker */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Docker (Sandboxed Terminal)</Typography>
                  <FormControlLabel
                    control={<Switch checked={form.docker_enabled} onChange={handleChange("docker_enabled")} />}
                    label="Enable Docker Terminal"
                  />
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                    Each chat session gets its own isolated container that persists across commands and is automatically removed after the idle timeout.
                  </Typography>
                  {form.docker_enabled && (
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="Docker URL"
                        value={form.docker_url || ""}
                        onChange={handleChange("docker_url")}
                        placeholder="unix:///var/run/docker.sock or tcp://host:2375"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="Container Image"
                        value={form.docker_image ?? "python:3.12-slim"}
                        onChange={handleChange("docker_image")}
                        helperText="Base image for sandbox containers"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="Idle Timeout (seconds)" type="number" inputProps={{ min: 60 }}
                        value={form.docker_timeout || 900}
                        onChange={handleChange("docker_timeout")}
                        helperText="Remove containers after this many seconds of inactivity"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label="Network Mode"
                        value={form.docker_network ?? "none"}
                        onChange={handleChange("docker_network")}
                        helperText={'"none" for no network access, "bridge" for internet access, or a custom network name'}
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.docker_read_only} onChange={handleChange("docker_read_only")} />}
                        label="Read-only rootfs"
                      />
                      <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                        Safer sandbox. Disable to let the LLM run <code>pip install</code> and write to the container filesystem.
                      </FormHelperText>
                    </Grid>
                    <Grid item xs={12}>
                      <Button
                        variant="outlined"
                        size="small"
                        disabled={!form.docker_url || dockerTest === "testing"}
                        onClick={() => {
                          setDockerTest("testing");
                          api.post("/settings/docker/test", {}, auth.user.token)
                            .then((d) => setDockerTest({ status: "ok", detail: `Connected (Docker ${d.server_version})` }))
                            .catch((e) => setDockerTest({ status: "error", detail: e?.detail || "Connection failed" }));
                        }}
                      >
                        {dockerTest === "testing" ? "Testing..." : "Test Connection"}
                      </Button>
                      {dockerTest && dockerTest !== "testing" && (
                        <Typography
                          variant="caption"
                          sx={{ ml: 2, color: dockerTest.status === "ok" ? "success.main" : "error.main" }}
                        >
                          {dockerTest.detail}
                        </Typography>
                      )}
                    </Grid>
                  </Grid>
                  )}
                </Card>
              </Grid>
            </Grid>
          )}

          {/* ===== AUTHENTICATION TAB ===== */}
          {active === "Authentication" && (
            <Grid container spacing={3}>
              {/* Core auth settings */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Local Authentication</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={4}>
                      <FormControlLabel
                        control={<Switch checked={form.auth_disable_local} onChange={handleChange("auth_disable_local")} />}
                        label="Disable Local Auth"
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        When enabled, only SSO login is allowed
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <FormControlLabel
                        control={<Switch checked={form.enforce_2fa} onChange={handleChange("enforce_2fa")} />}
                        label="Enforce 2FA"
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        Require TOTP two-factor authentication for all local users
                      </Typography>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* SSO general */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>Single Sign-On</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={4}>
                      <FormControlLabel
                        control={<Switch checked={form.sso_auto_create_user} onChange={handleChange("sso_auto_create_user")} />}
                        label="Auto Create Users"
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        Automatically create user accounts on first SSO login
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <TextField fullWidth label="Allowed Domains" value={form.sso_allowed_domains}
                        onChange={handleChange("sso_allowed_domains")} helperText="Comma-separated email domains, or * for all" />
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <FormControlLabel
                        control={<Switch checked={form.sso_auto_restricted} onChange={handleChange("sso_auto_restricted")} />}
                        label="Restrict New Users"
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        Auto-created SSO users will be in restricted (read-only) mode
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <FormControl fullWidth>
                        <InputLabel>Default Team</InputLabel>
                        <Select value={form.sso_auto_team_id || ""} onChange={handleChange("sso_auto_team_id")} label="Default Team">
                          <MenuItem value="">None</MenuItem>
                          {teams.map((t) => (
                            <MenuItem key={t.id} value={String(t.id)}>{t.name}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                        Auto-created SSO users will be added to this team
                      </Typography>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* SSO — Google */}
              <Grid item xs={12}>
                <Card elevation={1}>
                  <CollapsibleCardHeader icon={Security} title="Google" section="google" />
                  <Collapse in={expanded.google}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client ID" value={form.sso_google_client_id} onChange={handleChange("sso_google_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client Secret" type="password" value={form.sso_google_client_secret} onChange={handleChange("sso_google_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Redirect URI" value={form.sso_google_redirect_uri} onChange={handleChange("sso_google_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Scope" value={form.sso_google_scope} onChange={handleChange("sso_google_scope")} />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>

              {/* SSO — Microsoft */}
              <Grid item xs={12}>
                <Card elevation={1}>
                  <CollapsibleCardHeader icon={Security} title="Microsoft" section="microsoft" />
                  <Collapse in={expanded.microsoft}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client ID" value={form.sso_microsoft_client_id} onChange={handleChange("sso_microsoft_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client Secret" type="password" value={form.sso_microsoft_client_secret} onChange={handleChange("sso_microsoft_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Tenant ID" value={form.sso_microsoft_tenant_id} onChange={handleChange("sso_microsoft_tenant_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Redirect URI" value={form.sso_microsoft_redirect_uri} onChange={handleChange("sso_microsoft_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Scope" value={form.sso_microsoft_scope} onChange={handleChange("sso_microsoft_scope")} />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>

              {/* SSO — GitHub */}
              <Grid item xs={12}>
                <Card elevation={1}>
                  <CollapsibleCardHeader icon={Security} title="GitHub" section="github" />
                  <Collapse in={expanded.github}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client ID" value={form.sso_github_client_id} onChange={handleChange("sso_github_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client Secret" type="password" value={form.sso_github_client_secret} onChange={handleChange("sso_github_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Redirect URI" value={form.sso_github_redirect_uri} onChange={handleChange("sso_github_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Scope" value={form.sso_github_scope} onChange={handleChange("sso_github_scope")} />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>

              {/* SSO — Generic OIDC */}
              <Grid item xs={12}>
                <Card elevation={1}>
                  <CollapsibleCardHeader icon={Security} title="Generic OIDC" section="oidc" />
                  <Collapse in={expanded.oidc}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client ID" value={form.sso_oidc_client_id} onChange={handleChange("sso_oidc_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Client Secret" type="password" value={form.sso_oidc_client_secret} onChange={handleChange("sso_oidc_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Provider URL" value={form.sso_oidc_provider_url}
                            onChange={handleChange("sso_oidc_provider_url")} helperText="OpenID Connect discovery URL" />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Redirect URI" value={form.sso_oidc_redirect_uri} onChange={handleChange("sso_oidc_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Scopes" value={form.sso_oidc_scopes} onChange={handleChange("sso_oidc_scopes")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Provider Name" value={form.sso_oidc_provider_name}
                            onChange={handleChange("sso_oidc_provider_name")} helperText="Display name on login button" />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label="Email Claim" value={form.sso_oidc_email_claim} onChange={handleChange("sso_oidc_email_claim")} />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>
            </Grid>
          )}

          {/* Telemetry */}
          <Grid item xs={12}>
            <Card elevation={1} sx={{ p: 3 }}>
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>Telemetry</Typography>
              <Typography variant="body2" color="text.secondary">
                RESTai sends anonymized, aggregate usage statistics to help the open-source project understand adoption and prioritize development.
                No personal data, prompts, answers, or API keys are ever sent — only counts (projects, users, LLMs) and feature flags.
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                Status: <strong>{telemetryEnabled === null ? "..." : telemetryEnabled ? "Enabled" : "Disabled"}</strong>
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                To opt out, set the <code>ANONYMIZED_TELEMETRY=false</code> environment variable and restart the server.
              </Typography>
            </Card>
          </Grid>

          {/* Save button — always visible */}
          <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 3 }}>
            <Button variant="contained" color="primary" onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save Settings"}
            </Button>
          </Box>
        </Grid>
      </Grid>
    </Container>
  );
}
