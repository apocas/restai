import { useState, useEffect, useRef } from "react";
import {
  Grid, styled, Box, Card, Divider, TextField, Button,
  Switch, FormControlLabel, FormHelperText, Typography, Select, MenuItem, InputLabel, FormControl,
  Collapse, IconButton
} from "@mui/material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useTranslation } from "react-i18next";
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

export default function SettingsPage() {
  const { t } = useTranslation();
  const auth = useAuth();
  const { refreshCapabilities } = usePlatformCapabilities();
  const [active, setActive] = useState("general");

  const TABS = [
    { key: "general", name: t("settings.sections.general"), Icon: SettingsIcon },
    { key: "authentication", name: t("settings.sections.authentication"), Icon: Security },
  ];

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
    browser_enabled: false,
    browser_image: "mcr.microsoft.com/playwright/python:v1.48.0-jammy",
    browser_network: "bridge",
    browser_timeout: 900,
    system_llm: "",
    enforce_2fa: false,
  });
  const [teams, setTeams] = useState([]);
  const [llms, setLlms] = useState([]);
  const [saving, setSaving] = useState(false);
  const [dockerTest, setDockerTest] = useState(null); // null | "testing" | {status, detail}
  const [telemetryEnabled, setTelemetryEnabled] = useState(null);
  const [expanded, setExpanded] = useState({ google: false, microsoft: false, github: false, oidc: false });

  // Refs for deep-linkable sections. Hash like `#microsoft` auto-opens
  // the Authentication tab, expands the Microsoft card, and scrolls to
  // it. Useful for copy-pasting "go to my SSO setup" links in Slack /
  // support tickets.
  const sectionRefs = {
    google: useRef(null),
    microsoft: useRef(null),
    github: useRef(null),
    oidc: useRef(null),
  };

  // Map each deep-linkable hash to the tab it lives on. Extend this
  // when you add a new section that deserves a bookmark.
  const _SECTION_TAB = {
    google: "authentication",
    microsoft: "authentication",
    github: "authentication",
    oidc: "authentication",
  };

  const toggleExpanded = (section) => () => {
    setExpanded((prev) => ({ ...prev, [section]: !prev[section] }));
    // Reflect the current section in the URL so the user can bookmark /
    // share it. `replaceState` instead of `pushState` so expand/collapse
    // clicks don't pollute history.
    if (typeof window !== "undefined") {
      const targetHash = expanded[section] ? "" : `#${section}`;
      window.history.replaceState(null, "", window.location.pathname + window.location.search + targetHash);
    }
  };

  // Drive the tab + section state from `window.location.hash`. Runs on
  // mount and on hashchange so users who paste a deep-link mid-session
  // (or hit the browser back button) land on the right section.
  useEffect(() => {
    const applyHash = () => {
      const hash = (window.location.hash || "").replace(/^#/, "");
      if (!hash) return;
      const targetTab = _SECTION_TAB[hash];
      if (targetTab) setActive(targetTab);
      if (hash in sectionRefs) {
        setExpanded((prev) => ({ ...prev, [hash]: true }));
        // Give React a beat to render the expanded card before scrolling.
        setTimeout(() => {
          sectionRefs[hash].current?.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 80);
      }
    };
    applyHash();
    window.addEventListener("hashchange", applyHash);
    return () => window.removeEventListener("hashchange", applyHash);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
        toast.success(t("settings.saved"));
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
        <Breadcrumb routeSegments={[{ name: t("settings.title"), path: "/settings" }]} />
      </Box>

      <Grid container spacing={3}>
        <Grid item md={2} xs={12}>
          <ProjectTabNav tabs={TABS} active={active} setActive={setActive} />
        </Grid>

        <Grid item md={10} xs={12}>
          {/* ===== GENERAL TAB ===== */}
          {active === "general" && (
            <Grid container spacing={3}>
              {/* App */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.platform")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.appName")} value={form.app_name} onChange={handleChange("app_name")} />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <FormControlLabel
                        control={<Switch checked={form.hide_branding} onChange={handleChange("hide_branding")} />}
                        label={t("settings.fields.hideBranding")}
                      />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <FormControl fullWidth>
                        <InputLabel>{t("settings.fields.currency")}</InputLabel>
                        <Select value={form.currency} label={t("settings.fields.currency")} onChange={handleChange("currency")}>
                          <MenuItem value="USD">USD ($)</MenuItem>
                          <MenuItem value="EUR">EUR (&euro;)</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <FormControl fullWidth>
                        <InputLabel>{t("settings.fields.systemLlm")}</InputLabel>
                        <Select
                          value={form.system_llm ?? ""}
                          label={t("settings.fields.systemLlm")}
                          onChange={handleChange("system_llm")}
                        >
                          <MenuItem value=""><em>{t("common.none")}</em></MenuItem>
                          {llms.map((l) => (
                            <MenuItem key={l.id || l.name} value={l.name}>{l.name}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                        {t("settings.helpers.systemLlm")}
                      </Typography>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* LLM Proxy */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.proxy")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={form.proxy_enabled} onChange={handleChange("proxy_enabled")} />}
                        label={t("settings.fields.enableProxy")}
                      />
                    </Grid>
                    {form.proxy_enabled && (
                      <>
                        <Grid item xs={12} md={4}>
                          <TextField fullWidth label={t("settings.fields.proxyUrl")} value={form.proxy_url} onChange={handleChange("proxy_url")} />
                        </Grid>
                        <Grid item xs={12} md={4}>
                          <TextField fullWidth label={t("settings.fields.proxyKey")} type="password" value={form.proxy_key} onChange={handleChange("proxy_key")} />
                        </Grid>
                        <Grid item xs={12} md={4}>
                          <TextField fullWidth label={t("settings.fields.proxyTeamId")} value={form.proxy_team_id} onChange={handleChange("proxy_team_id")} />
                        </Grid>
                      </>
                    )}
                  </Grid>
                </Card>
              </Grid>

              {/* Limits */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.limits")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.maxAudioUploadSize")} type="number" inputProps={{ min: 1 }}
                        value={form.max_audio_upload_size} onChange={handleChange("max_audio_upload_size")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.dataRetentionDays")} type="number" inputProps={{ min: 0 }}
                        value={form.data_retention_days} onChange={handleChange("data_retention_days")}
                        helperText={t("settings.helpers.retention")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* Redis */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.redis")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.redisHost")} placeholder={t("settings.fields.redisHostPlaceholder")}
                        value={form.redis_host} onChange={handleChange("redis_host")} />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label={t("settings.fields.redisPort")} value={form.redis_port} onChange={handleChange("redis_port")} />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label={t("settings.fields.redisPassword")} type="password" value={form.redis_password} onChange={handleChange("redis_password")} />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label={t("settings.fields.redisDatabase")} value={form.redis_database} onChange={handleChange("redis_database")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* MCP */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>{t("settings.sections.mcp")}</Typography>
                  <FormControlLabel
                    control={<Switch checked={form.mcp_enabled} onChange={handleChange("mcp_enabled")} />}
                    label={t("settings.fields.enableMcp")}
                  />
                  <Typography variant="caption" color="text.secondary" display="block">
                    Expose projects as MCP tools at /mcp/sse. Requires server restart.
                  </Typography>
                </Card>
              </Grid>

              {/* Docker */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>{t("settings.sections.docker")}</Typography>
                  <FormControlLabel
                    control={<Switch checked={form.docker_enabled} onChange={handleChange("docker_enabled")} />}
                    label={t("settings.fields.enableDocker")}
                  />
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                    Each chat session gets its own isolated container that persists across commands and is automatically removed after the idle timeout.
                  </Typography>
                  {form.docker_enabled && (
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.dockerUrl")}
                        value={form.docker_url || ""}
                        onChange={handleChange("docker_url")}
                        placeholder={t("settings.fields.dockerUrlPlaceholder")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.containerImage")}
                        value={form.docker_image ?? "python:3.12-slim"}
                        onChange={handleChange("docker_image")}
                        helperText={t("settings.helpers.containerImage")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.idleTimeout")} type="number" inputProps={{ min: 60 }}
                        value={form.docker_timeout || 900}
                        onChange={handleChange("docker_timeout")}
                        helperText={t("settings.helpers.dockerTimeout")}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.networkMode")}
                        value={form.docker_network ?? "none"}
                        onChange={handleChange("docker_network")}
                        helperText={'"none" for no network access, "bridge" for internet access, or a custom network name'}
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.docker_read_only} onChange={handleChange("docker_read_only")} />}
                        label={t("settings.fields.readOnlyRootfs")}
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
                        {dockerTest === "testing" ? t("settings.fields.testing") : t("settings.fields.testDocker")}
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

              {/* Agentic Browser — Playwright + Chromium per-chat container */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.browser")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.browser_enabled} onChange={handleChange("browser_enabled")} />}
                        label={t("settings.fields.enableBrowser")}
                      />
                      <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                        Powers the <code>browser_*</code> builtin tools (goto, fill, click, screenshot, etc.).
                        Reuses the Docker daemon configured above. Image is pulled on first use.
                      </FormHelperText>
                    </Grid>
                    {form.browser_enabled && (
                      <>
                        <Grid item xs={12} md={6}>
                          <TextField
                            fullWidth
                            label={t("settings.fields.browserImage")}
                            value={form.browser_image ?? "mcr.microsoft.com/playwright/python:v1.48.0-jammy"}
                            onChange={handleChange("browser_image")}
                            helperText={t("settings.helpers.browserImage")}
                          />
                        </Grid>
                        <Grid item xs={12} md={3}>
                          <TextField
                            fullWidth
                            label={t("settings.fields.browserNetwork")}
                            value={form.browser_network ?? "bridge"}
                            onChange={handleChange("browser_network")}
                            helperText={"'bridge' for outbound (required — Chromium fetches remote sites). 'none' = offline only."}
                          />
                        </Grid>
                        <Grid item xs={12} md={3}>
                          <TextField
                            fullWidth
                            type="number"
                            label={t("settings.fields.browserTimeout")}
                            inputProps={{ min: 60 }}
                            value={form.browser_timeout ?? 900}
                            onChange={handleChange("browser_timeout")}
                            helperText={t("settings.helpers.browserTimeout")}
                          />
                        </Grid>
                      </>
                    )}
                  </Grid>
                </Card>
              </Grid>
            </Grid>
          )}

          {/* ===== AUTHENTICATION TAB ===== */}
          {active === "authentication" && (
            <Grid container spacing={3}>
              {/* Core auth settings */}
              <Grid item xs={12}>
                <Card elevation={1} sx={{ p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.localAuth")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={4}>
                      <FormControlLabel
                        control={<Switch checked={form.auth_disable_local} onChange={handleChange("auth_disable_local")} />}
                        label={t("settings.fields.disableLocalAuth")}
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        When enabled, only SSO login is allowed
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <FormControlLabel
                        control={<Switch checked={form.enforce_2fa} onChange={handleChange("enforce_2fa")} />}
                        label={t("settings.fields.enforce2fa")}
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
                        label={t("settings.fields.autoCreateUsers")}
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        Automatically create user accounts on first SSO login
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <TextField fullWidth label={t("settings.fields.allowedDomains")} value={form.sso_allowed_domains}
                        onChange={handleChange("sso_allowed_domains")} helperText={t("settings.helpers.allowedDomains")} />
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <FormControlLabel
                        control={<Switch checked={form.sso_auto_restricted} onChange={handleChange("sso_auto_restricted")} />}
                        label={t("settings.fields.restrictNewUsers")}
                      />
                      <Typography variant="caption" color="text.secondary" display="block">
                        Auto-created SSO users will be in restricted (read-only) mode
                      </Typography>
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <FormControl fullWidth>
                        <InputLabel>{t("settings.fields.defaultTeam")}</InputLabel>
                        <Select value={form.sso_auto_team_id || ""} onChange={handleChange("sso_auto_team_id")} label={t("settings.fields.defaultTeam")}>
                          <MenuItem value="">{t("common.none")}</MenuItem>
                          {teams.map((team) => (
                            <MenuItem key={team.id} value={String(team.id)}>{team.name}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                        {t("settings.helpers.autoTeam")}
                      </Typography>
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              {/* SSO — Google */}
              <Grid item xs={12}>
                <Card elevation={1} ref={sectionRefs.google}>
                  <CollapsibleCardHeader icon={Security} title="Google" section="google" />
                  <Collapse in={expanded.google}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientId")} value={form.sso_google_client_id} onChange={handleChange("sso_google_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientSecret")} type="password" value={form.sso_google_client_secret} onChange={handleChange("sso_google_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.redirectUri")} value={form.sso_google_redirect_uri} onChange={handleChange("sso_google_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.scope")} value={form.sso_google_scope} onChange={handleChange("sso_google_scope")} />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>

              {/* SSO — Microsoft */}
              <Grid item xs={12}>
                <Card elevation={1} ref={sectionRefs.microsoft}>
                  <CollapsibleCardHeader icon={Security} title="Microsoft" section="microsoft" />
                  <Collapse in={expanded.microsoft}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientId")} value={form.sso_microsoft_client_id} onChange={handleChange("sso_microsoft_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientSecret")} type="password" value={form.sso_microsoft_client_secret} onChange={handleChange("sso_microsoft_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.tenantId")} value={form.sso_microsoft_tenant_id} onChange={handleChange("sso_microsoft_tenant_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.redirectUri")} value={form.sso_microsoft_redirect_uri} onChange={handleChange("sso_microsoft_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.scope")} value={form.sso_microsoft_scope} onChange={handleChange("sso_microsoft_scope")} />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>

              {/* SSO — GitHub */}
              <Grid item xs={12}>
                <Card elevation={1} ref={sectionRefs.github}>
                  <CollapsibleCardHeader icon={Security} title="GitHub" section="github" />
                  <Collapse in={expanded.github}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientId")} value={form.sso_github_client_id} onChange={handleChange("sso_github_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientSecret")} type="password" value={form.sso_github_client_secret} onChange={handleChange("sso_github_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.redirectUri")} value={form.sso_github_redirect_uri} onChange={handleChange("sso_github_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.scope")} value={form.sso_github_scope} onChange={handleChange("sso_github_scope")} />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>

              {/* SSO — Generic OIDC */}
              <Grid item xs={12}>
                <Card elevation={1} ref={sectionRefs.oidc}>
                  <CollapsibleCardHeader icon={Security} title={t("settings.sections.oidc")} section="oidc" />
                  <Collapse in={expanded.oidc}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientId")} value={form.sso_oidc_client_id} onChange={handleChange("sso_oidc_client_id")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.clientSecret")} type="password" value={form.sso_oidc_client_secret} onChange={handleChange("sso_oidc_client_secret")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.providerUrl")} value={form.sso_oidc_provider_url}
                            onChange={handleChange("sso_oidc_provider_url")} helperText={t("settings.helpers.oidcProviderUrl")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.redirectUri")} value={form.sso_oidc_redirect_uri} onChange={handleChange("sso_oidc_redirect_uri")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.scopes")} value={form.sso_oidc_scopes} onChange={handleChange("sso_oidc_scopes")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.providerName")} value={form.sso_oidc_provider_name}
                            onChange={handleChange("sso_oidc_provider_name")} helperText={t("settings.helpers.oidcProviderName")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.emailClaim")} value={form.sso_oidc_email_claim} onChange={handleChange("sso_oidc_email_claim")} />
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
              <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>{t("settings.sections.telemetry")}</Typography>
              <Typography variant="body2" color="text.secondary">
                {t("settings.telemetry.description")}
              </Typography>
              <Typography variant="body2" sx={{ mt: 1 }}>
                {t("settings.helpers.telemetryStatus", { status: telemetryEnabled === null ? "..." : telemetryEnabled ? t("settings.status.enabled") : t("settings.status.disabled") })}
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
                {t("settings.telemetry.optOut")}
              </Typography>
            </Card>
          </Grid>

          {/* Save button — always visible */}
          <Box sx={{ display: "flex", justifyContent: "flex-end", mt: 3 }}>
            <Button variant="contained" color="primary" onClick={handleSave} disabled={saving}>
              {saving ? t("settings.helpers.saving") : t("settings.helpers.saveSettings")}
            </Button>
          </Box>
        </Grid>
      </Grid>
    </Container>
  );
}
