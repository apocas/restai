import { useState, useEffect } from "react";
import {
  Grid, styled, Box, Card, Divider, TextField, Button,
  Switch, FormControlLabel, Typography, Select, MenuItem, InputLabel, FormControl,
  Collapse, IconButton
} from "@mui/material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { toast } from "react-toastify";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";
import { Settings as SettingsIcon, Storage, Security, ExpandMore, ExpandLess } from "@mui/icons-material";
import { H4 } from "app/components/Typography";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

export default function SettingsPage() {
  const auth = useAuth();
  const { refreshCapabilities } = usePlatformCapabilities();

  const [form, setForm] = useState({
    app_name: "RESTai",
    hide_branding: false,
    proxy_enabled: false,
    proxy_url: "",
    proxy_key: "",
    proxy_team_id: "",
    agent_max_iterations: 20,
    max_audio_upload_size: 10,
    currency: "EUR",
    redis_host: "",
    redis_port: "6379",
    redis_password: "",
    redis_database: "0",
    // Auth
    auth_disable_local: false,
    sso_auto_create_user: false,
    sso_allowed_domains: "*",
    // Google
    sso_google_client_id: "",
    sso_google_client_secret: "",
    sso_google_redirect_uri: "",
    sso_google_scope: "openid email profile",
    // Microsoft
    sso_microsoft_client_id: "",
    sso_microsoft_client_secret: "",
    sso_microsoft_tenant_id: "",
    sso_microsoft_redirect_uri: "",
    sso_microsoft_scope: "openid email profile",
    // GitHub
    sso_github_client_id: "",
    sso_github_client_secret: "",
    sso_github_redirect_uri: "",
    sso_github_scope: "user:email",
    // OIDC
    sso_oidc_client_id: "",
    sso_oidc_client_secret: "",
    sso_oidc_provider_url: "",
    sso_oidc_redirect_uri: "",
    sso_oidc_scopes: "openid email profile",
    sso_oidc_provider_name: "SSO",
    sso_oidc_email_claim: "email",
  });
  const [saving, setSaving] = useState(false);

  // Collapsible state for SSO sections
  const [expanded, setExpanded] = useState({
    google: false,
    microsoft: false,
    github: false,
    oidc: false,
  });

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
  }, []);

  const handleChange = (field) => (e) => {
    const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = () => {
    setSaving(true);
    const body = { ...form };
    // Convert numeric fields
    body.agent_max_iterations = parseInt(body.agent_max_iterations, 10) || 20;
    body.max_audio_upload_size = parseInt(body.max_audio_upload_size, 10) || 10;

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

      <ContentBox>
        <Grid container spacing={3}>
          {/* General */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <FlexBox>
                <SettingsIcon sx={{ ml: 2 }} />
                <H4 sx={{ p: 2 }}>General</H4>
              </FlexBox>
              <Divider />
              <Box sx={{ p: 3 }}>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="App Name"
                      value={form.app_name}
                      onChange={handleChange("app_name")}
                    />
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={form.hide_branding}
                          onChange={handleChange("hide_branding")}
                        />
                      }
                      label="Hide Branding"
                    />
                  </Grid>
                  <Grid item xs={12} md={3}>
                    <FormControl fullWidth>
                      <InputLabel>Currency</InputLabel>
                      <Select
                        value={form.currency}
                        label="Currency"
                        onChange={handleChange("currency")}
                      >
                        <MenuItem value="USD">USD ($)</MenuItem>
                        <MenuItem value="EUR">EUR (&euro;)</MenuItem>
                      </Select>
                    </FormControl>
                  </Grid>
                </Grid>
              </Box>
            </Card>
          </Grid>

          {/* LLM Proxy */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <FlexBox>
                <SettingsIcon sx={{ ml: 2 }} />
                <H4 sx={{ p: 2 }}>LLM Proxy</H4>
              </FlexBox>
              <Divider />
              <Box sx={{ p: 3 }}>
                <Grid container spacing={3}>
                  <Grid item xs={12}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={form.proxy_enabled}
                          onChange={handleChange("proxy_enabled")}
                        />
                      }
                      label="Enable Proxy"
                    />
                  </Grid>
                  {form.proxy_enabled && (
                    <>
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          label="Proxy URL"
                          value={form.proxy_url}
                          onChange={handleChange("proxy_url")}
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          label="Proxy Key"
                          type="password"
                          value={form.proxy_key}
                          onChange={handleChange("proxy_key")}
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <TextField
                          fullWidth
                          label="Proxy Team ID"
                          value={form.proxy_team_id}
                          onChange={handleChange("proxy_team_id")}
                        />
                      </Grid>
                    </>
                  )}
                </Grid>
              </Box>
            </Card>
          </Grid>

          {/* Limits */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <FlexBox>
                <SettingsIcon sx={{ ml: 2 }} />
                <H4 sx={{ p: 2 }}>Limits</H4>
              </FlexBox>
              <Divider />
              <Box sx={{ p: 3 }}>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Agent Max Iterations"
                      type="number"
                      inputProps={{ min: 1 }}
                      value={form.agent_max_iterations}
                      onChange={handleChange("agent_max_iterations")}
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Max Audio Upload Size (MB)"
                      type="number"
                      inputProps={{ min: 1 }}
                      value={form.max_audio_upload_size}
                      onChange={handleChange("max_audio_upload_size")}
                    />
                  </Grid>
                </Grid>
              </Box>
            </Card>
          </Grid>

          {/* Chat History (Redis) */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <FlexBox>
                <Storage sx={{ ml: 2 }} />
                <H4 sx={{ p: 2 }}>Chat History (Redis)</H4>
              </FlexBox>
              <Divider />
              <Box sx={{ p: 3 }}>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Redis Host"
                      placeholder="Leave empty for in-memory"
                      value={form.redis_host}
                      onChange={handleChange("redis_host")}
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Redis Port"
                      value={form.redis_port}
                      onChange={handleChange("redis_port")}
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Redis Password"
                      type="password"
                      value={form.redis_password}
                      onChange={handleChange("redis_password")}
                    />
                  </Grid>
                  <Grid item xs={12} md={6}>
                    <TextField
                      fullWidth
                      label="Redis Database"
                      value={form.redis_database}
                      onChange={handleChange("redis_database")}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <Typography variant="caption" color="text.secondary">
                      Configure Redis for persistent chat history. Leave host empty to use in-memory storage.
                    </Typography>
                  </Grid>
                </Grid>
              </Box>
            </Card>
          </Grid>

          {/* Authentication */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <FlexBox>
                <Security sx={{ ml: 2 }} />
                <H4 sx={{ p: 2 }}>Authentication</H4>
              </FlexBox>
              <Divider />
              <Box sx={{ p: 3 }}>
                <Grid container spacing={3}>
                  <Grid item xs={12} md={4}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={form.auth_disable_local}
                          onChange={handleChange("auth_disable_local")}
                        />
                      }
                      label="Disable Local Auth"
                    />
                    <Typography variant="caption" color="text.secondary" display="block">
                      When enabled, only SSO login is allowed
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <FormControlLabel
                      control={
                        <Switch
                          checked={form.sso_auto_create_user}
                          onChange={handleChange("sso_auto_create_user")}
                        />
                      }
                      label="Auto Create Users"
                    />
                    <Typography variant="caption" color="text.secondary" display="block">
                      Automatically create user accounts on first SSO login
                    </Typography>
                  </Grid>
                  <Grid item xs={12} md={4}>
                    <TextField
                      fullWidth
                      label="Allowed Domains"
                      value={form.sso_allowed_domains}
                      onChange={handleChange("sso_allowed_domains")}
                      helperText="Comma-separated email domains, or * for all"
                    />
                  </Grid>
                </Grid>
              </Box>
            </Card>
          </Grid>

          {/* SSO — Google */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <CollapsibleCardHeader icon={Security} title="SSO — Google" section="google" />
              <Divider />
              <Collapse in={expanded.google}>
                <Box sx={{ p: 3 }}>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client ID"
                        value={form.sso_google_client_id}
                        onChange={handleChange("sso_google_client_id")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client Secret"
                        type="password"
                        value={form.sso_google_client_secret}
                        onChange={handleChange("sso_google_client_secret")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Redirect URI"
                        value={form.sso_google_redirect_uri}
                        onChange={handleChange("sso_google_redirect_uri")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Scope"
                        value={form.sso_google_scope}
                        onChange={handleChange("sso_google_scope")}
                      />
                    </Grid>
                  </Grid>
                </Box>
              </Collapse>
            </Card>
          </Grid>

          {/* SSO — Microsoft */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <CollapsibleCardHeader icon={Security} title="SSO — Microsoft" section="microsoft" />
              <Divider />
              <Collapse in={expanded.microsoft}>
                <Box sx={{ p: 3 }}>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client ID"
                        value={form.sso_microsoft_client_id}
                        onChange={handleChange("sso_microsoft_client_id")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client Secret"
                        type="password"
                        value={form.sso_microsoft_client_secret}
                        onChange={handleChange("sso_microsoft_client_secret")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Tenant ID"
                        value={form.sso_microsoft_tenant_id}
                        onChange={handleChange("sso_microsoft_tenant_id")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Redirect URI"
                        value={form.sso_microsoft_redirect_uri}
                        onChange={handleChange("sso_microsoft_redirect_uri")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Scope"
                        value={form.sso_microsoft_scope}
                        onChange={handleChange("sso_microsoft_scope")}
                      />
                    </Grid>
                  </Grid>
                </Box>
              </Collapse>
            </Card>
          </Grid>

          {/* SSO — GitHub */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <CollapsibleCardHeader icon={Security} title="SSO — GitHub" section="github" />
              <Divider />
              <Collapse in={expanded.github}>
                <Box sx={{ p: 3 }}>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client ID"
                        value={form.sso_github_client_id}
                        onChange={handleChange("sso_github_client_id")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client Secret"
                        type="password"
                        value={form.sso_github_client_secret}
                        onChange={handleChange("sso_github_client_secret")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Redirect URI"
                        value={form.sso_github_redirect_uri}
                        onChange={handleChange("sso_github_redirect_uri")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Scope"
                        value={form.sso_github_scope}
                        onChange={handleChange("sso_github_scope")}
                      />
                    </Grid>
                  </Grid>
                </Box>
              </Collapse>
            </Card>
          </Grid>

          {/* SSO — Generic OIDC */}
          <Grid item xs={12}>
            <Card elevation={3}>
              <CollapsibleCardHeader icon={Security} title="SSO — Generic OIDC" section="oidc" />
              <Divider />
              <Collapse in={expanded.oidc}>
                <Box sx={{ p: 3 }}>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client ID"
                        value={form.sso_oidc_client_id}
                        onChange={handleChange("sso_oidc_client_id")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Client Secret"
                        type="password"
                        value={form.sso_oidc_client_secret}
                        onChange={handleChange("sso_oidc_client_secret")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Provider URL"
                        value={form.sso_oidc_provider_url}
                        onChange={handleChange("sso_oidc_provider_url")}
                        helperText="OpenID Connect discovery URL"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Redirect URI"
                        value={form.sso_oidc_redirect_uri}
                        onChange={handleChange("sso_oidc_redirect_uri")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Scopes"
                        value={form.sso_oidc_scopes}
                        onChange={handleChange("sso_oidc_scopes")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Provider Name"
                        value={form.sso_oidc_provider_name}
                        onChange={handleChange("sso_oidc_provider_name")}
                        helperText="Display name on login button"
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Email Claim"
                        value={form.sso_oidc_email_claim}
                        onChange={handleChange("sso_oidc_email_claim")}
                      />
                    </Grid>
                  </Grid>
                </Box>
              </Collapse>
            </Card>
          </Grid>

          {/* Save */}
          <Grid item xs={12}>
            <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
              <Button
                variant="contained"
                color="primary"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? "Saving..." : "Save Settings"}
              </Button>
            </Box>
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
