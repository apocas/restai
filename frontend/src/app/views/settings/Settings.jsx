import { useState, useEffect, useRef } from "react";
import {
  Grid, styled, Box, Card, Divider, TextField, Button,
  Switch, FormControlLabel, FormHelperText, Typography, Select, MenuItem, InputLabel, FormControl,
  Collapse, IconButton, InputAdornment, Tooltip
} from "@mui/material";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import api from "app/utils/api";
import { Settings as SettingsIcon, Storage, Security, Mail, Payment, ExpandMore, ExpandLess, CloudUpload, Close as CloseIcon } from "@mui/icons-material";
import { H4 } from "app/components/Typography";
import ProjectTabNav from "app/views/projects/components/ProjectTabNav";
import { forensicCardSx, loadFonts } from "app/views/projects/components/forensic/styles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
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
    { key: "vectordbs", name: t("settings.sections.vectordbs"), Icon: Storage },
    { key: "notifications", name: t("settings.sections.notifications"), Icon: Mail },
    { key: "payments", name: t("settings.sections.payments"), Icon: Payment },
    { key: "authentication", name: t("settings.sections.authentication"), Icon: Security },
  ];

  const [form, setForm] = useState({
    app_name: "RESTai",
    logo_url: "",
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
    app_docker_enabled: false,
    app_docker_image: "restai/app-runtime:2",
    app_docker_idle_timeout: 1800,
    system_llm: "",
    enforce_2fa: false,
    vectordb_chromadb_enabled: true,
    vectordb_chromadb_host: "",
    vectordb_chromadb_port: "",
    vectordb_pgvector_enabled: false,
    vectordb_pgvector_host: "",
    vectordb_pgvector_port: "5432",
    vectordb_pgvector_user: "",
    vectordb_pgvector_password: "",
    vectordb_pgvector_db: "restai_vectors",
    vectordb_weaviate_enabled: false,
    vectordb_weaviate_host: "",
    vectordb_weaviate_port: "8080",
    vectordb_weaviate_grpc_port: "50051",
    vectordb_weaviate_api_key: "",
    vectordb_pinecone_enabled: false,
    vectordb_pinecone_api_key: "",
    vectordb_pinecone_index: "",
    ldap_enabled: false,
    ldap_server_host: "",
    ldap_server_port: "",
    ldap_attribute_for_mail: "mail",
    ldap_attribute_for_username: "uid",
    ldap_search_base: "",
    ldap_search_filters: "",
    ldap_app_dn: "",
    ldap_app_password: "",
    ldap_use_tls: false,
    ldap_ca_cert_file: "",
    ldap_ciphers: "",
    smtp_host: "",
    smtp_port: "587",
    smtp_user: "",
    smtp_password: "",
    smtp_from: "",
    email_default_to: "",
    payment_enabled: false,
    payment_stripe_enabled: false,
    payment_stripe_secret_key: "",
    payment_stripe_publishable_key: "",
    payment_stripe_webhook_secret: "",
    payment_paypal_enabled: false,
    payment_paypal_client_id: "",
    payment_paypal_client_secret: "",
    payment_paypal_webhook_id: "",
    payment_paypal_mode: "sandbox",
  });
  const [teams, setTeams] = useState([]);
  const [llms, setLlms] = useState([]);
  const [saving, setSaving] = useState(false);
  const [dockerTest, setDockerTest] = useState(null); // null | "testing" | {status, detail}
  const [telemetryEnabled, setTelemetryEnabled] = useState(null);
  const [expanded, setExpanded] = useState({ google: false, microsoft: false, github: false, oidc: false, ldap: false });

  // Hash like `#microsoft` auto-opens Authentication, expands the card, and
  // scrolls to it (deep-linkable from Slack / support tickets).
  const sectionRefs = {
    google: useRef(null),
    microsoft: useRef(null),
    github: useRef(null),
    oidc: useRef(null),
    ldap: useRef(null),
  };

  const _SECTION_TAB = {
    google: "authentication",
    microsoft: "authentication",
    github: "authentication",
    oidc: "authentication",
    ldap: "authentication",
  };

  const toggleExpanded = (section) => () => {
    setExpanded((prev) => ({ ...prev, [section]: !prev[section] }));
    // replaceState (not pushState) so expand/collapse doesn't pollute history.
    if (typeof window !== "undefined") {
      const targetHash = expanded[section] ? "" : `#${section}`;
      window.history.replaceState(null, "", window.location.pathname + window.location.search + targetHash);
    }
  };

  useEffect(() => {
    const applyHash = () => {
      const hash = (window.location.hash || "").replace(/^#/, "");
      if (!hash) return;
      const targetTab = _SECTION_TAB[hash];
      if (targetTab) setActive(targetTab);
      if (hash in sectionRefs) {
        setExpanded((prev) => ({ ...prev, [hash]: true }));
        // Wait for the expand to render before scrolling.
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

  // Same downscale flow as TeamEdit so the result fits the Pydantic 300k cap.
  // PNG stays PNG (transparency), other rasters → canvas JPEG q=0.88, SVGs verbatim.
  const [logoUploading, setLogoUploading] = useState(false);
  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      toast.error(t("settings.logoNotImage") || "That file isn't an image.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      toast.error(t("settings.logoTooLarge") || "Logo file is over 8 MB.");
      return;
    }
    setLogoUploading(true);
    try {
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });
      if (file.type === "image/svg+xml") {
        setForm((s) => ({ ...s, logo_url: dataUrl }));
        toast.success(t("settings.logoUploaded") || "Logo uploaded.");
        return;
      }
      const img = await new Promise((resolve, reject) => {
        const i = new window.Image();
        i.onload = () => resolve(i);
        i.onerror = reject;
        i.src = dataUrl;
      });
      const MAX = 512;
      let { width, height } = img;
      if (width > MAX || height > MAX) {
        const scale = MAX / Math.max(width, height);
        width = Math.round(width * scale);
        height = Math.round(height * scale);
      }
      const canvas = document.createElement("canvas");
      canvas.width = width;
      canvas.height = height;
      canvas.getContext("2d").drawImage(img, 0, 0, width, height);
      const isPng = file.type === "image/png";
      const out = canvas.toDataURL(isPng ? "image/png" : "image/jpeg", isPng ? undefined : 0.88);
      if (out.length > 290000) {
        toast.error(t("settings.logoTooLargeAfterScale") || "Logo is too large even after downscaling. Try a smaller or simpler image.");
        return;
      }
      setForm((s) => ({ ...s, logo_url: out }));
      toast.success(t("settings.logoUploaded") || "Logo uploaded.");
    } catch {
      toast.error(t("settings.logoFailed") || "Failed to read the image.");
    } finally {
      setLogoUploading(false);
    }
  };

  const handleSave = () => {
    setSaving(true);
    const body = { ...form };
    body.max_audio_upload_size = parseInt(body.max_audio_upload_size, 10) || 10;
    body.data_retention_days = parseInt(body.data_retention_days, 10) || 0;
    body.docker_timeout = parseInt(body.docker_timeout, 10) || 900;
    body.app_docker_idle_timeout = parseInt(body.app_docker_idle_timeout, 10) || 1800;

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
      <PageHero
        icon={<SettingsIcon sx={{ color: "#fff" }} />}
        eyebrow="PLATFORM CONFIG"
        title={t("settings.title") || "Settings"}
        subtitle="GUI-managed runtime configuration. Saved to the DB, applied across workers immediately."
        showStatusDot
        statusLabel="Live"
      />

      <Grid container spacing={3}>
        <Grid item md={2} xs={12}>
          <ProjectTabNav tabs={TABS} active={active} setActive={setActive} />
        </Grid>

        <Grid item md={10} xs={12}>
          {active === "general" && (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.platform")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.appName")} value={form.app_name} onChange={handleChange("app_name")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label={t("settings.fields.loginLogo") || "Login Logo"}
                        value={form.logo_url || ""}
                        onChange={handleChange("logo_url")}
                        placeholder="https://… or upload →"
                        helperText={t("settings.fields.loginLogoHelp") || "Shown on the login page. URL or upload (auto-downscaled). Leave empty for the default."}
                        InputProps={{
                          startAdornment: form.logo_url ? (
                            <InputAdornment position="start">
                              <Box
                                component="img"
                                src={form.logo_url}
                                alt=""
                                sx={{
                                  width: 28, height: 28,
                                  objectFit: "contain",
                                  borderRadius: 0.75,
                                  border: "1px solid rgba(15,23,42,0.10)",
                                  background: "rgba(15,23,42,0.03)",
                                  p: 0.25,
                                }}
                              />
                            </InputAdornment>
                          ) : undefined,
                          endAdornment: (
                            <InputAdornment position="end">
                              {form.logo_url && (
                                <Tooltip title={t("settings.logoClear") || "Remove logo"}>
                                  <IconButton
                                    size="small"
                                    onClick={() => setForm((s) => ({ ...s, logo_url: "" }))}
                                    sx={{ mr: 0.25 }}
                                  >
                                    <CloseIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              )}
                              <Tooltip title={t("settings.logoUpload") || "Upload logo"}>
                                <IconButton size="small" component="label" disabled={logoUploading}>
                                  <CloudUpload fontSize="small" />
                                  <input
                                    hidden
                                    type="file"
                                    accept="image/*"
                                    onChange={handleLogoUpload}
                                  />
                                </IconButton>
                              </Tooltip>
                            </InputAdornment>
                          ),
                        }}
                      />
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.appBuilder")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.app_docker_enabled} onChange={handleChange("app_docker_enabled")} />}
                        label={t("settings.fields.enableAppBuilder")}
                      />
                      <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                        {t("settings.helpers.appBuilder")}
                      </FormHelperText>
                    </Grid>
                    {form.app_docker_enabled && (
                      <>
                        <Grid item xs={12} md={8}>
                          <TextField
                            fullWidth
                            label={t("settings.fields.appBuilderImage")}
                            value={form.app_docker_image ?? "restai/app-runtime:2"}
                            onChange={handleChange("app_docker_image")}
                            helperText={t("settings.helpers.appBuilderImage")}
                          />
                        </Grid>
                        <Grid item xs={12} md={4}>
                          <TextField
                            fullWidth
                            type="number"
                            label={t("settings.fields.appBuilderIdleTimeout")}
                            inputProps={{ min: 60 }}
                            value={form.app_docker_idle_timeout ?? 1800}
                            onChange={handleChange("app_docker_idle_timeout")}
                            helperText={t("settings.helpers.appBuilderIdleTimeout")}
                          />
                        </Grid>
                      </>
                    )}
                  </Grid>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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
            </Grid>
          )}

          {active === "vectordbs" && (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Typography variant="body2" color="text.secondary">
                  {t("settings.helpers.vectordbsIntro")}
                </Typography>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.chromadb")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.vectordb_chromadb_enabled} onChange={handleChange("vectordb_chromadb_enabled")} />}
                        label={t("settings.fields.vectordbEnabled")}
                      />
                      <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                        {t("settings.helpers.chromadbEnabled")}
                      </FormHelperText>
                    </Grid>
                    <Grid item xs={12} md={9}>
                      <TextField fullWidth label={t("settings.fields.vectordbChromadbHost")}
                        placeholder={t("settings.fields.vectordbChromadbHostPlaceholder")}
                        value={form.vectordb_chromadb_host || ""} onChange={handleChange("vectordb_chromadb_host")}
                        helperText={t("settings.helpers.vectordbChromadbHost")} />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField fullWidth label={t("settings.fields.vectordbChromadbPort")}
                        value={form.vectordb_chromadb_port || ""} onChange={handleChange("vectordb_chromadb_port")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.pgvector")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.vectordb_pgvector_enabled} onChange={handleChange("vectordb_pgvector_enabled")} />}
                        label={t("settings.fields.vectordbEnabled")}
                      />
                      <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                        {t("settings.helpers.pgvectorEnabled")}
                      </FormHelperText>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.vectordbPgvectorHost")}
                        value={form.vectordb_pgvector_host || ""} onChange={handleChange("vectordb_pgvector_host")} />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label={t("settings.fields.vectordbPgvectorPort")}
                        value={form.vectordb_pgvector_port || ""} onChange={handleChange("vectordb_pgvector_port")} />
                    </Grid>
                    <Grid item xs={12} md={4}>
                      <TextField fullWidth label={t("settings.fields.vectordbPgvectorDb")}
                        value={form.vectordb_pgvector_db || ""} onChange={handleChange("vectordb_pgvector_db")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.vectordbPgvectorUser")}
                        value={form.vectordb_pgvector_user || ""} onChange={handleChange("vectordb_pgvector_user")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth type="password" label={t("settings.fields.vectordbPgvectorPassword")}
                        value={form.vectordb_pgvector_password || ""} onChange={handleChange("vectordb_pgvector_password")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.weaviate")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.vectordb_weaviate_enabled} onChange={handleChange("vectordb_weaviate_enabled")} />}
                        label={t("settings.fields.vectordbEnabled")}
                      />
                      <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                        {t("settings.helpers.weaviateEnabled")}
                      </FormHelperText>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.vectordbWeaviateHost")}
                        value={form.vectordb_weaviate_host || ""} onChange={handleChange("vectordb_weaviate_host")} />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField fullWidth label={t("settings.fields.vectordbWeaviatePort")}
                        value={form.vectordb_weaviate_port || ""} onChange={handleChange("vectordb_weaviate_port")} />
                    </Grid>
                    <Grid item xs={12} md={3}>
                      <TextField fullWidth label={t("settings.fields.vectordbWeaviateGrpcPort")}
                        value={form.vectordb_weaviate_grpc_port || ""} onChange={handleChange("vectordb_weaviate_grpc_port")} />
                    </Grid>
                    <Grid item xs={12}>
                      <TextField fullWidth type="password" label={t("settings.fields.vectordbWeaviateApiKey")}
                        value={form.vectordb_weaviate_api_key || ""} onChange={handleChange("vectordb_weaviate_api_key")}
                        helperText={t("settings.helpers.vectordbWeaviateApiKey")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.pinecone")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12}>
                      <FormControlLabel
                        control={<Switch checked={!!form.vectordb_pinecone_enabled} onChange={handleChange("vectordb_pinecone_enabled")} />}
                        label={t("settings.fields.vectordbEnabled")}
                      />
                      <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                        {t("settings.helpers.pineconeEnabled")}
                      </FormHelperText>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth type="password" label={t("settings.fields.vectordbPineconeApiKey")}
                        value={form.vectordb_pinecone_api_key || ""} onChange={handleChange("vectordb_pinecone_api_key")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.vectordbPineconeIndex")}
                        value={form.vectordb_pinecone_index || ""} onChange={handleChange("vectordb_pinecone_index")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>
            </Grid>
          )}

          {active === "notifications" && (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Typography variant="body2" color="text.secondary">
                  {t("settings.helpers.notificationsIntro")}
                </Typography>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>{t("settings.sections.email")}</Typography>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={8}>
                      <TextField fullWidth label={t("settings.fields.smtpHost")}
                        value={form.smtp_host || ""} onChange={handleChange("smtp_host")}
                        placeholder="smtp.example.com" />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label={t("settings.fields.smtpPort")}
                        value={form.smtp_port || ""} onChange={handleChange("smtp_port")}
                        helperText="587 STARTTLS · 465 SMTPS" />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField fullWidth label={t("settings.fields.emailDefaultTo")}
                        value={form.email_default_to || ""} onChange={handleChange("email_default_to")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.smtpUser")}
                        value={form.smtp_user || ""} onChange={handleChange("smtp_user")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth type="password" label={t("settings.fields.smtpPassword")}
                        value={form.smtp_password || ""} onChange={handleChange("smtp_password")} />
                    </Grid>
                    <Grid item xs={12}>
                      <TextField fullWidth label={t("settings.fields.smtpFrom")}
                        value={form.smtp_from || ""} onChange={handleChange("smtp_from")}
                        placeholder='"RESTai" <ops@example.com>' />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>
            </Grid>
          )}

          {active === "payments" && (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Typography variant="body2" color="text.secondary">
                  {t("settings.helpers.paymentsIntro")}
                </Typography>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <FormControlLabel
                    control={<Switch checked={!!form.payment_enabled} onChange={handleChange("payment_enabled")} />}
                    label={t("settings.fields.paymentEnabled")}
                  />
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                    {t("settings.helpers.paymentWebhookHint")}
                  </Typography>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <FormControlLabel
                    control={<Switch checked={!!form.payment_stripe_enabled} onChange={handleChange("payment_stripe_enabled")} />}
                    label={t("settings.fields.stripeEnabled")}
                  />
                  <Grid container spacing={3} sx={{ mt: 0 }}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth type="password" label={t("settings.fields.stripeSecretKey")}
                        value={form.payment_stripe_secret_key || ""} onChange={handleChange("payment_stripe_secret_key")}
                        placeholder="sk_live_…" />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.stripePublishableKey")}
                        value={form.payment_stripe_publishable_key || ""} onChange={handleChange("payment_stripe_publishable_key")}
                        placeholder="pk_live_…" />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth type="password" label={t("settings.fields.stripeWebhookSecret")}
                        value={form.payment_stripe_webhook_secret || ""} onChange={handleChange("payment_stripe_webhook_secret")}
                        placeholder="whsec_…" helperText={t("settings.helpers.stripeWebhookHelp")} />
                    </Grid>
                  </Grid>
                </Card>
              </Grid>

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
                  <FormControlLabel
                    control={<Switch checked={!!form.payment_paypal_enabled} onChange={handleChange("payment_paypal_enabled")} />}
                    label={t("settings.fields.paypalEnabled")}
                  />
                  <Grid container spacing={3} sx={{ mt: 0 }}>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.paypalClientId")}
                        value={form.payment_paypal_client_id || ""} onChange={handleChange("payment_paypal_client_id")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth type="password" label={t("settings.fields.paypalClientSecret")}
                        value={form.payment_paypal_client_secret || ""} onChange={handleChange("payment_paypal_client_secret")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField fullWidth label={t("settings.fields.paypalWebhookId")}
                        value={form.payment_paypal_webhook_id || ""} onChange={handleChange("payment_paypal_webhook_id")}
                        helperText={t("settings.helpers.paypalWebhookHelp")} />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <FormControl fullWidth>
                        <InputLabel>{t("settings.fields.paypalMode")}</InputLabel>
                        <Select value={form.payment_paypal_mode || "sandbox"} label={t("settings.fields.paypalMode")}
                          onChange={handleChange("payment_paypal_mode")}>
                          <MenuItem value="sandbox">Sandbox</MenuItem>
                          <MenuItem value="live">Live</MenuItem>
                        </Select>
                      </FormControl>
                    </Grid>
                  </Grid>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
                    {t("settings.helpers.paypalAutoRechargeNote")}
                  </Typography>
                </Card>
              </Grid>
            </Grid>
          )}

          {active === "authentication" && (
            <Grid container spacing={3}>
              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={0} sx={{ ...forensicCardSx, p: 3 }}>
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

              <Grid item xs={12}>
                <Card elevation={1} ref={sectionRefs.ldap}>
                  <CollapsibleCardHeader icon={Security} title={t("settings.sections.ldap")} section="ldap" />
                  <Collapse in={expanded.ldap}>
                    <Divider />
                    <Box sx={{ p: 3 }}>
                      <Grid container spacing={3}>
                        <Grid item xs={12}>
                          <FormControlLabel
                            control={<Switch checked={!!form.ldap_enabled} onChange={handleChange("ldap_enabled")} />}
                            label={t("settings.fields.ldapEnabled")}
                          />
                          <FormHelperText sx={{ mt: -0.5, ml: 4 }}>
                            {t("settings.helpers.ldapEnabled")}
                          </FormHelperText>
                        </Grid>

                        <Grid item xs={12} md={8}>
                          <TextField fullWidth label={t("settings.fields.ldapServerHost")}
                            value={form.ldap_server_host || ""} onChange={handleChange("ldap_server_host")} />
                        </Grid>
                        <Grid item xs={12} md={2}>
                          <TextField fullWidth label={t("settings.fields.ldapServerPort")}
                            value={form.ldap_server_port || ""} onChange={handleChange("ldap_server_port")}
                            placeholder="389 / 636" />
                        </Grid>
                        <Grid item xs={12} md={2}>
                          <FormControlLabel
                            control={<Switch checked={!!form.ldap_use_tls} onChange={handleChange("ldap_use_tls")} />}
                            label={t("settings.fields.ldapUseTls")}
                          />
                        </Grid>

                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.ldapSearchBase")}
                            value={form.ldap_search_base || ""} onChange={handleChange("ldap_search_base")}
                            helperText={t("settings.helpers.ldapSearchBase")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.ldapSearchFilters")}
                            value={form.ldap_search_filters || ""} onChange={handleChange("ldap_search_filters")}
                            helperText={t("settings.helpers.ldapSearchFilters")} />
                        </Grid>

                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.ldapAttributeForUsername")}
                            value={form.ldap_attribute_for_username || ""} onChange={handleChange("ldap_attribute_for_username")}
                            helperText={t("settings.helpers.ldapAttributeForUsername")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.ldapAttributeForMail")}
                            value={form.ldap_attribute_for_mail || ""} onChange={handleChange("ldap_attribute_for_mail")}
                            helperText={t("settings.helpers.ldapAttributeForMail")} />
                        </Grid>

                        <Grid item xs={12} md={6}>
                          <TextField fullWidth label={t("settings.fields.ldapAppDn")}
                            value={form.ldap_app_dn || ""} onChange={handleChange("ldap_app_dn")}
                            helperText={t("settings.helpers.ldapAppDn")} />
                        </Grid>
                        <Grid item xs={12} md={6}>
                          <TextField fullWidth type="password" label={t("settings.fields.ldapAppPassword")}
                            value={form.ldap_app_password || ""} onChange={handleChange("ldap_app_password")} />
                        </Grid>

                        <Grid item xs={12} md={8}>
                          <TextField fullWidth label={t("settings.fields.ldapCaCertFile")}
                            value={form.ldap_ca_cert_file || ""} onChange={handleChange("ldap_ca_cert_file")}
                            helperText={t("settings.helpers.ldapCaCertFile")} />
                        </Grid>
                        <Grid item xs={12} md={4}>
                          <TextField fullWidth label={t("settings.fields.ldapCiphers")}
                            value={form.ldap_ciphers || ""} onChange={handleChange("ldap_ciphers")}
                            placeholder="ALL" />
                        </Grid>
                      </Grid>
                    </Box>
                  </Collapse>
                </Card>
              </Grid>

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
