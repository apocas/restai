import { useState, useEffect } from "react";
import {
  Autocomplete, Box, Button, Card, Chip, CircularProgress, Grid,
  IconButton, InputAdornment, Tab, Tabs, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import {
  Group, Code, Psychology, Palette, Star, Image, Speaker,
  Save, Close, Send, GroupsOutlined, AttachMoney, Workspaces,
  AllInclusive, Mail, CloudUpload,
} from "@mui/icons-material";
import api from "app/utils/api";
import PageHero from "app/components/page/PageHero";
import { FONT_MONO, cleanCardSx, pulse } from "app/components/page/pageStyles";

const ACCENT = "#0891b2";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Hover lift disabled — full-page surface, not a list tile.
const sectionCardSx = {
  ...cleanCardSx,
  p: 0,
  "&:hover": { transform: "none", borderColor: "divider", boxShadow: "none" },
};

function SectionHeader({ icon: Icon, title, subtitle, count, action }) {
  return (
    <Box
      sx={{
        px: 2.5, pt: 2, pb: 1.75,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: "1px solid",
        borderColor: "divider",
        flexWrap: "wrap",
      }}
    >
      {Icon && (
        <Icon sx={{ fontSize: 18, color: "text.secondary", flexShrink: 0 }} />
      )}
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography sx={{ fontSize: "0.95rem", fontWeight: 700, color: "text.primary", lineHeight: 1.2 }}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.3 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {count != null && (
        <Box
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            fontWeight: 600,
            color: "text.secondary",
            px: 0.9, py: 0.25,
            borderRadius: 0.75,
            background: "rgba(15,23,42,0.04)",
            border: "1px solid rgba(15,23,42,0.08)",
          }}
        >
          {count}
        </Box>
      )}
      {action}
    </Box>
  );
}

function PickerField({ label, placeholder, options, value, onChange, getOptionLabel = (o) => o.name, isOptionEqualToValue, helperText }) {
  return (
    <>
      <Autocomplete
        multiple
        options={options}
        getOptionLabel={getOptionLabel}
        value={value}
        onChange={(_, v) => onChange(v)}
        filterSelectedOptions
        isOptionEqualToValue={isOptionEqualToValue}
        renderTags={(picked, getTagProps) =>
          picked.map((opt, idx) => {
            const tagProps = getTagProps({ index: idx });
            return (
              <Chip
                {...tagProps}
                key={tagProps.key}
                label={getOptionLabel(opt)}
                size="small"
                sx={{ borderRadius: 0.75 }}
              />
            );
          })
        }
        renderInput={(params) => (
          <TextField {...params} variant="outlined" label={label} placeholder={placeholder} />
        )}
      />
      {helperText && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.75 }}>
          {helperText}
        </Typography>
      )}
    </>
  );
}

function TabPanel({ children, value, index }) {
  if (value !== index) return null;
  return <Box sx={{ p: 2.5 }}>{children}</Box>;
}

function SubSection({ icon, title, count, children }) {
  return (
    <Box sx={{ p: 0 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.25 }}>
        {icon}
        <Typography sx={{ fontSize: "0.85rem", fontWeight: 700, color: "text.primary" }}>
          {title}
        </Typography>
        {count != null && (
          <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.7rem", color: "text.secondary", ml: 0.25 }}>
            · {count}
          </Typography>
        )}
      </Box>
      {children}
    </Box>
  );
}

export default function TeamEdit() {
  const { t } = useTranslation();
  const { id } = useParams();
  const isNewTeam = id === undefined;
  const [team, setTeam] = useState({
    name: "",
    description: "",
    budget: -1,
    users: [],
    admins: [],
    projects: [],
    llms: [],
    embeddings: [],
    image_generators: [],
    audio_generators: [],
    branding: { primary_color: "", secondary_color: "", logo_url: "", welcome_message: "", app_name: "" },
    options: { smtp_host: "", smtp_port: "", smtp_user: "", smtp_password: "", smtp_from: "", email_default_to: "" },
  });
  const [logoUploading, setLogoUploading] = useState(false);

  // Client-side downscale so a phone screenshot doesn't bust the Pydantic
  // max_length cap. PNG stays PNG (transparency), other rasters → JPEG 0.88.
  const handleLogoUpload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      toast.error(t("teams.edit.logoNotImage") || "That file isn't an image.");
      return;
    }
    if (file.size > 8 * 1024 * 1024) {
      toast.error(t("teams.edit.logoTooLarge") || "Logo file is over 8 MB.");
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
        setTeam((s) => ({ ...s, branding: { ...s.branding, logo_url: dataUrl } }));
        toast.success(t("teams.edit.logoUploaded") || "Logo uploaded.");
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
        toast.error(t("teams.edit.logoTooLargeAfterScale") || "Logo is too large even after downscaling. Try a smaller or simpler image.");
        return;
      }
      setTeam((s) => ({ ...s, branding: { ...s.branding, logo_url: out } }));
      toast.success(t("teams.edit.logoUploaded") || "Logo uploaded.");
    } catch {
      toast.error(t("teams.edit.logoFailed") || "Failed to read the image.");
    } finally {
      setLogoUploading(false);
    }
  };

  const [users, setUsers] = useState([]);
  const [projects, setProjects] = useState([]);
  const [llms, setLLMs] = useState([]);
  const [embeddings, setEmbeddings] = useState([]);
  const [imageGenerators, setImageGenerators] = useState([]);
  const [audioGenerators, setAudioGenerators] = useState([]);
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [inviteUsername, setInviteUsername] = useState("");

  const navigate = useNavigate();
  const auth = useAuth();
  const user = auth.user;

  const handleInvite = () => {
    if (!inviteUsername.trim()) return;
    api.post(`/teams/${id}/invitations`, { username: inviteUsername.trim() }, auth.user.token)
      .then((data) => {
        toast.success(data.message || t("invitations.sent"));
        setInviteUsername("");
      })
      .catch(() => {});
  };

  const fetchTeam = async () => {
    if (isNewTeam) { setLoading(false); return; }
    try {
      const data = await api.get(`/teams/${id}`, user.token);
      setTeam({
        ...data,
        users: data.users || [],
        admins: data.admins || [],
        projects: data.projects || [],
        llms: data.llms || [],
        embeddings: data.embeddings || [],
        image_generators: (data.image_generators || []).map((g) => ({ name: g })),
        audio_generators: (data.audio_generators || []).map((g) => ({ name: g })),
        branding: data.branding || { primary_color: "", secondary_color: "", logo_url: "", welcome_message: "", app_name: "" },
        options: data.options || { smtp_host: "", smtp_port: "", smtp_user: "", smtp_password: "", smtp_from: "", email_default_to: "" },
      });
      setLoading(false);
    } catch (e) { setLoading(false); }
  };

  const fetchUsers     = async () => { try { const d = await api.get("/users",    user.token); setUsers(d.users); } catch {} };
  const fetchProjects  = async () => { try { const d = await api.get("/projects", user.token); setProjects(d.projects); } catch {} };
  const fetchModels    = async () => { try { const d = await api.get("/info",     user.token); setLLMs(d.llms); setEmbeddings(d.embeddings); } catch {} };
  const fetchGenerators = async () => {
    try { const d = await api.get("/image", user.token, { silent: true }); setImageGenerators((d.generators || []).map((g) => ({ name: g }))); } catch {}
    try { const d = await api.get("/audio", user.token, { silent: true }); setAudioGenerators((d.generators || []).map((g) => ({ name: g }))); } catch {}
  };

  useEffect(() => {
    Promise.all([fetchTeam(), fetchUsers(), fetchProjects(), fetchModels(), fetchGenerators()]);
    // eslint-disable-next-line
  }, [id]);

  useEffect(() => {
    document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - ${isNewTeam ? t("teams.edit.newTitle") : t("teams.edit.editTitle")}`;
  }, [isNewTeam, t]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setTeam({ ...team, [name]: value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        name: team.name,
        description: team.description,
        budget: parseFloat(team.budget),
        users: team.users.map((u) => u.username),
        admins: team.admins.map((a) => a.username),
        projects: team.projects.map((p) => p.name),
        llms: team.llms.map((l) => l.name),
        embeddings: team.embeddings.map((e2) => e2.name),
        image_generators: team.image_generators.map((g) => g.name),
        audio_generators: team.audio_generators.map((g) => g.name),
        branding: team.branding,
        options: team.options,
      };
      const endpoint = isNewTeam ? "/teams" : `/teams/${id}`;
      const data = isNewTeam
        ? await api.post(endpoint, payload, user.token)
        : await api.patch(endpoint, payload, user.token);
      toast.success(isNewTeam ? t("teams.edit.created") : t("teams.edit.updated"));
      navigate(isNewTeam ? `/team/${data.id}` : `/team/${id}`);
    } catch (e2) {} finally { setSaving(false); }
  };

  const handleCancel = () => navigate(isNewTeam ? "/teams" : `/team/${id}`);

  if (loading) {
    return (
      <Container>
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", py: 12, gap: 2 }}>
          <Box
            sx={{
              width: 56, height: 56,
              borderRadius: "50%",
              background: "rgba(15,23,42,0.04)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              animation: `${pulse} 2s ease-out infinite`,
            }}
          >
            <CircularProgress size={24} sx={{ color: "text.secondary" }} />
          </Box>
          <Typography
            sx={{
              fontFamily: FONT_MONO, fontSize: "0.7rem",
              color: "text.disabled", letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {t("common.loading")}
          </Typography>
        </Box>
      </Container>
    );
  }

  const hasBudget = team.budget >= 0;
  const heroEyebrow = isNewTeam ? "TEAM/NEW" : `TEAM/${String(id).padStart(4, "0")}`;
  const heroTitle = isNewTeam ? t("teams.edit.newTitle") : team.name || t("teams.edit.editTitle");

  const heroStats = [
    { glyph: "◆", color: "#cbd5e1", label: `${(team.users || []).length} member${(team.users || []).length === 1 ? "" : "s"}` },
    { glyph: "★", color: "#cbd5e1", label: `${(team.admins || []).length} admin${(team.admins || []).length === 1 ? "" : "s"}` },
    { glyph: "⌬", color: "#cbd5e1", label: `${(team.projects || []).length} project${(team.projects || []).length === 1 ? "" : "s"}` },
    hasBudget
      ? { glyph: "$", color: "#cbd5e1", label: `$${parseFloat(team.budget).toFixed(2)} cap` }
      : { glyph: "∞", color: "#94a3b8", label: t("teams.view.unlimited") },
  ];

  return (
    <Container>
      <form onSubmit={handleSubmit}>
        <PageHero
          icon={<GroupsOutlined sx={{ color: "#fff" }} />}
          eyebrow={heroEyebrow}
          title={heroTitle}
          subtitle={
            isNewTeam
              ? t("teams.edit.newSubtitle") || "Provision a new workspace, pick members, attach models."
              : t("teams.edit.editSubtitle") || "Adjust membership, allocations, and branding."
          }
          stats={heroStats}
          actions={
            <Box sx={{ display: "flex", gap: 1 }}>
              <Button
                variant="outlined"
                startIcon={<Close />}
                onClick={handleCancel}
                sx={{
                  textTransform: "none",
                  color: "#fff",
                  borderColor: "rgba(255,255,255,0.4)",
                  "&:hover": { borderColor: "#fff", backgroundColor: "rgba(255,255,255,0.08)" },
                }}
              >
                {t("common.cancel")}
              </Button>
              <Button
                type="submit"
                variant="contained"
                startIcon={saving ? <CircularProgress size={14} color="inherit" /> : <Save />}
                disabled={saving}
                sx={{
                  textTransform: "none",
                  fontWeight: 600,
                  backgroundColor: "#fff",
                  color: "#0f172a",
                  boxShadow: "none",
                  "&:hover": { backgroundColor: "rgba(255,255,255,0.92)", boxShadow: "none" },
                  "&.Mui-disabled": { backgroundColor: "rgba(255,255,255,0.5)", color: "rgba(15,23,42,0.5)" },
                }}
              >
                {saving
                  ? t("common.saving") || "Saving…"
                  : isNewTeam ? t("teams.edit.createTeam") : t("teams.edit.saveChanges")}
              </Button>
            </Box>
          }
          compact
        />

        {/* GENERAL — name, description, budget */}
        <Card variant="outlined" sx={{ ...sectionCardSx, mt: 2.5 }}>
          <SectionHeader
            icon={GroupsOutlined}
            title={t("teams.edit.tabs.general") || "General"}
            subtitle={t("teams.edit.generalSubtitle") || "Team identity and budget cap"}
          />
          <Box sx={{ p: 2.5 }}>
            <Grid container spacing={2}>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label={t("teams.edit.name")}
                  name="name"
                  value={team.name}
                  onChange={handleChange}
                  required
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label={t("teams.edit.budget")}
                  name="budget"
                  type="number"
                  value={team.budget}
                  onChange={handleChange}
                  inputProps={{ step: "0.01" }}
                  helperText={t("teams.edit.budgetHelp")}
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        {hasBudget
                          ? <AttachMoney sx={{ color: "text.secondary", fontSize: 18 }} />
                          : <AllInclusive sx={{ color: "text.disabled", fontSize: 18 }} />}
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label={t("teams.edit.description")}
                  name="description"
                  value={team.description || ""}
                  onChange={handleChange}
                  multiline
                  rows={3}
                />
              </Grid>
            </Grid>
          </Box>
        </Card>

        {/* TABS */}
        <Card variant="outlined" sx={{ ...sectionCardSx, mt: 2.5 }}>
          <Box sx={{ borderBottom: "1px solid", borderColor: "divider", px: 1.5 }}>
            <Tabs
              value={tabValue}
              onChange={(_, v) => setTabValue(v)}
              TabIndicatorProps={{ sx: { height: 2, borderRadius: 1, backgroundColor: ACCENT } }}
              sx={{
                minHeight: 48,
                "& .MuiTab-root": {
                  textTransform: "none",
                  fontWeight: 600,
                  fontSize: "0.85rem",
                  color: "text.secondary",
                  minHeight: 48,
                  "&.Mui-selected": { color: ACCENT },
                },
              }}
            >
              <Tab label={t("teams.edit.tabs.users")}    icon={<Group />}     iconPosition="start" />
              <Tab label={t("teams.edit.tabs.projects")} icon={<Code />}      iconPosition="start" />
              <Tab label={t("teams.edit.tabs.models")}   icon={<Psychology />} iconPosition="start" />
              <Tab label={t("teams.edit.tabs.branding")} icon={<Palette />}    iconPosition="start" />
              <Tab label={t("teams.edit.tabs.integrations")} icon={<Mail />}   iconPosition="start" />
            </Tabs>
          </Box>

          {/* USERS / ADMINS / INVITE */}
          <TabPanel value={tabValue} index={0}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <SubSection
                  icon={<Group sx={{ fontSize: 18, color: "text.secondary" }} />}
                  title={t("teams.edit.members")}
                  count={(team.users || []).length}
                >
                  <PickerField
                    options={users}
                    value={team.users}
                    onChange={(v) => setTeam({ ...team, users: v })}
                    label={t("teams.edit.selectUsers")}
                    placeholder={t("teams.edit.tabs.users")}
                    getOptionLabel={(o) => o.username}
                    helperText={t("teams.edit.membersSubtitle") || "Everyone with read+write access"}
                  />
                </SubSection>
              </Grid>
              <Grid item xs={12} md={6}>
                <SubSection
                  icon={<Star sx={{ fontSize: 18, color: "text.secondary" }} />}
                  title={t("teams.edit.admins")}
                  count={(team.admins || []).length}
                >
                  <PickerField
                    options={users}
                    value={team.admins}
                    onChange={(v) => setTeam({ ...team, admins: v })}
                    label={t("teams.edit.selectAdmins")}
                    placeholder={t("teams.edit.admins")}
                    getOptionLabel={(o) => o.username}
                    helperText={t("teams.edit.adminsHelp")}
                  />
                </SubSection>
              </Grid>

              {!isNewTeam && (
                <Grid item xs={12}>
                  <Box
                    sx={{
                      mt: 1,
                      p: 2,
                      borderRadius: 1.5,
                      border: "1px solid",
                      borderColor: "divider",
                      background: "rgba(15,23,42,0.015)",
                    }}
                  >
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.25 }}>
                      <Send sx={{ fontSize: 18, color: "text.secondary" }} />
                      <Typography sx={{ fontSize: "0.85rem", fontWeight: 700 }}>
                        {t("teams.edit.invite")}
                      </Typography>
                    </Box>
                    <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1.25 }}>
                      {t("teams.edit.inviteHelp")}
                    </Typography>
                    <Box sx={{ display: "flex", gap: 1, alignItems: "stretch", flexWrap: "wrap" }}>
                      <TextField
                        size="small"
                        label={t("teams.edit.username")}
                        value={inviteUsername}
                        onChange={(e) => setInviteUsername(e.target.value)}
                        sx={{ minWidth: 280, flex: 1 }}
                      />
                      <Button
                        variant="contained"
                        startIcon={<Send />}
                        onClick={handleInvite}
                        disabled={!inviteUsername.trim()}
                        sx={{ textTransform: "none", fontWeight: 600, boxShadow: "none" }}
                      >
                        {t("teams.edit.sendInvite")}
                      </Button>
                    </Box>
                  </Box>
                </Grid>
              )}
            </Grid>
          </TabPanel>

          {/* PROJECTS */}
          <TabPanel value={tabValue} index={1}>
            <SubSection
              icon={<Workspaces sx={{ fontSize: 18, color: "text.secondary" }} />}
              title={t("teams.edit.projectsHeading")}
              count={(team.projects || []).length}
            >
              <PickerField
                options={projects}
                value={team.projects}
                onChange={(v) => setTeam({ ...team, projects: v })}
                label={t("teams.edit.selectProjects")}
                placeholder={t("teams.edit.tabs.projects")}
                helperText={t("teams.edit.projectsHelp")}
              />
            </SubSection>
          </TabPanel>

          {/* MODELS */}
          <TabPanel value={tabValue} index={2}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <SubSection
                  icon={<Psychology sx={{ fontSize: 18, color: "text.secondary" }} />}
                  title={t("teams.edit.llms")}
                  count={(team.llms || []).length}
                >
                  <PickerField
                    options={llms}
                    value={team.llms}
                    onChange={(v) => setTeam({ ...team, llms: v })}
                    label={t("teams.edit.selectLlms")}
                    placeholder={t("nav.llms")}
                  />
                </SubSection>
              </Grid>
              <Grid item xs={12} md={6}>
                <SubSection
                  icon={<Psychology sx={{ fontSize: 18, color: "text.secondary" }} />}
                  title={t("teams.edit.embeddings")}
                  count={(team.embeddings || []).length}
                >
                  <PickerField
                    options={embeddings}
                    value={team.embeddings}
                    onChange={(v) => setTeam({ ...team, embeddings: v })}
                    label={t("teams.edit.selectEmbeddings")}
                    placeholder={t("nav.embeddings")}
                  />
                </SubSection>
              </Grid>
              <Grid item xs={12} md={6}>
                <SubSection
                  icon={<Image sx={{ fontSize: 18, color: "text.secondary" }} />}
                  title={t("teams.edit.imageGen")}
                  count={(team.image_generators || []).length}
                >
                  {imageGenerators.length > 0 ? (
                    <PickerField
                      options={imageGenerators}
                      value={team.image_generators}
                      onChange={(v) => setTeam({ ...team, image_generators: v })}
                      label={t("teams.edit.selectImageGen")}
                      placeholder={t("teams.edit.imageGen")}
                      isOptionEqualToValue={(o, v) => o.name === v.name}
                    />
                  ) : (
                    <Typography variant="body2" sx={{ color: "text.disabled", fontStyle: "italic" }}>
                      {t("teams.edit.noImageGen")}
                    </Typography>
                  )}
                </SubSection>
              </Grid>
              <Grid item xs={12} md={6}>
                <SubSection
                  icon={<Speaker sx={{ fontSize: 18, color: "text.secondary" }} />}
                  title={t("teams.edit.audioGen")}
                  count={(team.audio_generators || []).length}
                >
                  {audioGenerators.length > 0 ? (
                    <PickerField
                      options={audioGenerators}
                      value={team.audio_generators}
                      onChange={(v) => setTeam({ ...team, audio_generators: v })}
                      label={t("teams.edit.selectAudioGen")}
                      placeholder={t("teams.edit.audioGen")}
                      isOptionEqualToValue={(o, v) => o.name === v.name}
                    />
                  ) : (
                    <Typography variant="body2" sx={{ color: "text.disabled", fontStyle: "italic" }}>
                      {t("teams.edit.noAudioGen")}
                    </Typography>
                  )}
                </SubSection>
              </Grid>
            </Grid>
          </TabPanel>

          {/* BRANDING */}
          <TabPanel value={tabValue} index={3}>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t("teams.edit.brandingHelp")}
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label={t("teams.edit.appName")}
                  value={team.branding?.app_name || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, app_name: e.target.value } })}
                  helperText={t("teams.edit.appNameHelp")}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label={t("teams.edit.logoUrl")}
                  value={team.branding?.logo_url || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, logo_url: e.target.value } })}
                  helperText={t("teams.edit.logoUrlHelp")}
                  InputProps={{
                    startAdornment: team.branding?.logo_url ? (
                      <InputAdornment position="start">
                        <Box
                          component="img"
                          src={team.branding.logo_url}
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
                        {team.branding?.logo_url && (
                          <Tooltip title={t("teams.edit.logoClear") || "Remove logo"}>
                            <IconButton
                              size="small"
                              onClick={() => setTeam((s) => ({ ...s, branding: { ...s.branding, logo_url: "" } }))}
                              sx={{ mr: 0.25 }}
                            >
                              <Close fontSize="small" />
                            </IconButton>
                          </Tooltip>
                        )}
                        <Tooltip title={t("teams.edit.logoUpload") || "Upload logo"}>
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
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label={t("teams.edit.primaryColor")}
                  value={team.branding?.primary_color || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, primary_color: e.target.value } })}
                  placeholder="#1976d2"
                  helperText={t("teams.edit.primaryColorHelp")}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <Box
                          sx={{
                            width: 28, height: 28,
                            borderRadius: 0.75,
                            border: "1px solid rgba(15,23,42,0.10)",
                            background: team.branding?.primary_color || "#1976d2",
                            position: "relative",
                            overflow: "hidden",
                          }}
                        >
                          <input
                            type="color"
                            value={team.branding?.primary_color || "#1976d2"}
                            onChange={(e) => setTeam({ ...team, branding: { ...team.branding, primary_color: e.target.value } })}
                            style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer", border: "none" }}
                          />
                        </Box>
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label={t("teams.edit.secondaryColor")}
                  value={team.branding?.secondary_color || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, secondary_color: e.target.value } })}
                  placeholder="#ff9800"
                  helperText={t("teams.edit.secondaryColorHelp")}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <Box
                          sx={{
                            width: 28, height: 28,
                            borderRadius: 0.75,
                            border: "1px solid rgba(15,23,42,0.10)",
                            background: team.branding?.secondary_color || "#ff9800",
                            position: "relative",
                            overflow: "hidden",
                          }}
                        >
                          <input
                            type="color"
                            value={team.branding?.secondary_color || "#ff9800"}
                            onChange={(e) => setTeam({ ...team, branding: { ...team.branding, secondary_color: e.target.value } })}
                            style={{ position: "absolute", inset: 0, opacity: 0, cursor: "pointer", border: "none" }}
                          />
                        </Box>
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label={t("teams.edit.welcomeMessage")}
                  value={team.branding?.welcome_message || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, welcome_message: e.target.value } })}
                  helperText={t("teams.edit.welcomeHelp")}
                />
              </Grid>

              {(team.branding?.logo_url || team.branding?.primary_color || team.branding?.app_name) && (
                <Grid item xs={12}>
                  <Typography
                    variant="caption"
                    sx={{
                      display: "block",
                      fontFamily: FONT_MONO,
                      fontSize: "0.62rem",
                      letterSpacing: "0.18em",
                      textTransform: "uppercase",
                      fontWeight: 700,
                      color: "text.disabled",
                      mb: 1,
                    }}
                  >
                    {t("teams.edit.preview")}
                  </Typography>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1.5,
                      p: 2,
                      borderRadius: 1.5,
                      border: "1px solid",
                      borderColor: "divider",
                      background: team.branding?.primary_color || "#1976d2",
                      color: "#fff",
                    }}
                  >
                    {team.branding?.logo_url
                      ? <img width="32" height="32" src={team.branding.logo_url} alt="logo" style={{ objectFit: "contain" }} />
                      : <img width="32" height="32" src="/admin/assets/images/restai-logo.png" alt="logo" />}
                    <Typography sx={{ color: "#fff", fontWeight: 700, fontSize: "1.1rem" }}>
                      {team.branding?.app_name || team.name || "RESTai"}
                    </Typography>
                  </Box>
                  {team.branding?.welcome_message && (
                    <Box
                      sx={{
                        mt: 1,
                        p: 1.5,
                        borderRadius: 1.5,
                        border: "1px solid",
                        borderColor: "divider",
                        background: "rgba(15,23,42,0.015)",
                        fontSize: "0.85rem",
                        color: "text.secondary",
                        fontStyle: "italic",
                      }}
                    >
                      {team.branding.welcome_message}
                    </Box>
                  )}
                </Grid>
              )}
            </Grid>
          </TabPanel>

          {/* INTEGRATIONS */}
          <TabPanel value={tabValue} index={4}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
              <Mail sx={{ fontSize: 18, color: "text.secondary" }} />
              <Typography sx={{ fontSize: "0.95rem", fontWeight: 700 }}>
                {t("teams.edit.email.title") || "Email (SMTP)"}
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {t("teams.edit.email.subtitle") || "Empty fields fall back to platform Notifications settings."}
            </Typography>
            <Grid container spacing={2}>
              <Grid item xs={12} md={8}>
                <TextField
                  fullWidth
                  label={t("settings.fields.smtpHost")}
                  placeholder="smtp.example.com"
                  value={team.options?.smtp_host || ""}
                  onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_host: e.target.value } })}
                />
              </Grid>
              <Grid item xs={12} md={2}>
                <TextField
                  fullWidth
                  label={t("settings.fields.smtpPort")}
                  placeholder="587"
                  value={team.options?.smtp_port || ""}
                  onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_port: e.target.value } })}
                />
              </Grid>
              <Grid item xs={12} md={2}>
                <TextField
                  fullWidth
                  label={t("settings.fields.emailDefaultTo")}
                  value={team.options?.email_default_to || ""}
                  onChange={(e) => setTeam({ ...team, options: { ...team.options, email_default_to: e.target.value } })}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  label={t("settings.fields.smtpUser")}
                  value={team.options?.smtp_user || ""}
                  onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_user: e.target.value } })}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                  fullWidth
                  type="password"
                  label={t("settings.fields.smtpPassword")}
                  value={team.options?.smtp_password || ""}
                  onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_password: e.target.value } })}
                  helperText={t("settings.helpers.smtpPasswordMasked") || "Saved password is shown as ****; leave that to keep it unchanged."}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  label={t("settings.fields.smtpFrom")}
                  placeholder='"Team Bot" <bot@example.com>'
                  value={team.options?.smtp_from || ""}
                  onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_from: e.target.value } })}
                />
              </Grid>
            </Grid>
          </TabPanel>
        </Card>
      </form>
    </Container>
  );
}
