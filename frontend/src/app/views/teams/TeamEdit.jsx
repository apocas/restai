import { useState, useEffect } from "react";
import {
  Autocomplete, Box, Button, Card, Chip, CircularProgress, Grid,
  InputAdornment, Tab, Tabs, TextField, Typography, styled,
} from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import {
  Group, Code, Psychology, Palette, Star, Image, Speaker,
  Save, Close, Send, GroupsOutlined, AttachMoney, Workspaces,
  AllInclusive, Mail,
} from "@mui/icons-material";
import api from "app/utils/api";
import PageHero from "app/components/page/PageHero";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

// Same fuchsia family as the Teams list / view pages so the trio
// reads as one tightly related cluster.
const ACCENT = "#c026d3";        // fuchsia-600
const ACCENT_DARK = "#a21caf";   // fuchsia-700
const ACCENT_SOFT = "rgba(192,38,211,0.10)";

// Per-section accents — same palette as TeamView so the edit form
// echoes the read page's visual taxonomy.
const SECTION = {
  members:    { c: "#7c3aed", soft: "rgba(124,58,237,0.10)" },
  admins:     { c: "#dc2626", soft: "rgba(220,38,38,0.10)"  },
  projects:   { c: ACCENT,    soft: ACCENT_SOFT             },
  llms:       { c: "#1d4ed8", soft: "rgba(29,78,216,0.10)"  },
  embeddings: { c: "#0d9488", soft: "rgba(13,148,136,0.10)" },
  imageGen:   { c: "#f43f5e", soft: "rgba(244,63,94,0.10)"  },
  audioGen:   { c: "#f59e0b", soft: "rgba(245,158,11,0.10)" },
  branding:   { c: "#0891b2", soft: "rgba(8,145,178,0.10)"  },
  integrations: { c: "#16a34a", soft: "rgba(22,163,74,0.10)"  },
  general:    { c: ACCENT,    soft: ACCENT_SOFT             },
};

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    pointerEvents: "none",
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

function TileHeader({ icon, title, subtitle, accent = ACCENT, count, action }) {
  return (
    <Box
      sx={{
        px: 2.5, pt: 2, pb: 1.75,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: "1px solid rgba(15,23,42,0.06)",
        flexWrap: "wrap",
      }}
    >
      <Box
        sx={{
          width: 36, height: 36, flexShrink: 0,
          borderRadius: 1.5,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${accent}1a`,
          color: accent,
          "& svg": { fontSize: 20 },
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: accent,
            lineHeight: 1,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.4 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {count != null && (
        <Box
          sx={{
            display: "inline-flex",
            alignItems: "center",
            px: 1, py: 0.4,
            borderRadius: 0.75,
            backgroundColor: `${accent}10`,
            border: `1px solid ${accent}33`,
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            fontWeight: 700,
            color: accent,
          }}
        >
          {count}
        </Box>
      )}
      {action}
    </Box>
  );
}

// Per-section text-field styling — focus ring picks up the section's
// accent so each tab feels colour-grounded.
const fieldSx = (accent) => ({
  "& .MuiOutlinedInput-root": {
    "& fieldset": { borderColor: "rgba(15,23,42,0.12)" },
    "&:hover fieldset": { borderColor: `${accent}55` },
    "&.Mui-focused fieldset": { borderColor: accent, borderWidth: 1.5 },
  },
  "& .MuiInputLabel-root.Mui-focused": { color: accent },
});

// Themed Autocomplete — section-tinted chips for picked items.
function PickerField({ label, placeholder, options, value, onChange, accent, getOptionLabel = (o) => o.name, isOptionEqualToValue, helperText }) {
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
                sx={{
                  fontFamily: FONT_MONO,
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  backgroundColor: `${accent}15`,
                  color: accent,
                  border: `1px solid ${accent}44`,
                  borderRadius: 0.75,
                  "& .MuiChip-deleteIcon": {
                    color: `${accent}88`,
                    "&:hover": { color: accent },
                  },
                }}
              />
            );
          })
        }
        renderInput={(params) => (
          <TextField
            {...params}
            variant="outlined"
            label={label}
            placeholder={placeholder}
            sx={fieldSx(accent)}
          />
        )}
      />
      {helperText && (
        <Typography
          variant="caption"
          sx={{
            display: "block",
            mt: 0.75,
            color: "text.secondary",
            fontFamily: FONT_MONO,
            fontSize: "0.66rem",
            letterSpacing: "0.04em",
          }}
        >
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
        // smtp_password arrives masked (****xxxx); update_team preserves the saved value when it sees that prefix.
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
              width: 64, height: 64,
              borderRadius: "50%",
              background: ACCENT_SOFT,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              animation: `${pulse} 2s ease-out infinite`,
            }}
          >
            <CircularProgress size={28} sx={{ color: ACCENT }} />
          </Box>
          <Box
            component="span"
            sx={{
              fontFamily: FONT_MONO,
              fontSize: "0.7rem",
              color: "text.secondary",
              letterSpacing: "0.1em",
              textTransform: "uppercase",
            }}
          >
            {t("common.loading")}
          </Box>
        </Box>
      </Container>
    );
  }

  const hasBudget = team.budget >= 0;
  const heroEyebrow = isNewTeam ? "TEAM/NEW" : `TEAM/${String(id).padStart(4, "0")}`;
  const heroTitle = isNewTeam ? t("teams.edit.newTitle") : team.name || t("teams.edit.editTitle");

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
          stats={[
            { glyph: "◆", color: "#f0abfc", label: `${(team.users || []).length} member${(team.users || []).length === 1 ? "" : "s"}` },
            { glyph: "★", color: "#fca5a5", label: `${(team.admins || []).length} admin${(team.admins || []).length === 1 ? "" : "s"}` },
            { glyph: "⌬", color: "#fcd34d", label: `${(team.projects || []).length} project${(team.projects || []).length === 1 ? "" : "s"}` },
            ...(hasBudget
              ? [{ glyph: "$", color: "#a7f3d0", label: `$${parseFloat(team.budget).toFixed(2)} cap` }]
              : [{ glyph: "∞", color: "#94a3b8", label: t("teams.view.unlimited") }]),
          ]}
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
                  fontWeight: 700,
                  background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                  boxShadow: `0 4px 14px ${ACCENT}66`,
                  "&:hover": {
                    background: `linear-gradient(135deg, ${ACCENT} 0%, #86198f 100%)`,
                    boxShadow: `0 6px 18px ${ACCENT}88`,
                  },
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
        <Box sx={{ mt: 2.5 }}>
          <TileCard elevation={0} accent={SECTION.general.c}>
            <TileHeader
              icon={<GroupsOutlined />}
              title={t("teams.edit.tabs.general") || "General"}
              subtitle={t("teams.edit.generalSubtitle") || "Team identity and budget cap"}
              accent={SECTION.general.c}
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
                    sx={fieldSx(SECTION.general.c)}
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
                            ? <AttachMoney sx={{ color: SECTION.general.c, fontSize: 18 }} />
                            : <AllInclusive sx={{ color: "text.disabled", fontSize: 18 }} />}
                        </InputAdornment>
                      ),
                    }}
                    sx={fieldSx(SECTION.general.c)}
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
                    sx={fieldSx(SECTION.general.c)}
                  />
                </Grid>
              </Grid>
            </Box>
          </TileCard>
        </Box>

        <Box sx={{ mt: 2.5 }}>
          <TileCard elevation={0} accent={ACCENT}>
            <Box sx={{ borderBottom: "1px solid rgba(15,23,42,0.06)", px: 1.5 }}>
              <Tabs
                value={tabValue}
                onChange={(_, v) => setTabValue(v)}
                TabIndicatorProps={{ sx: { background: `linear-gradient(90deg, ${ACCENT}, ${ACCENT_DARK})`, height: 3, borderRadius: 2 } }}
                sx={{
                  minHeight: 48,
                  "& .MuiTab-root": {
                    textTransform: "none",
                    fontWeight: 700,
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
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <TileCard elevation={0} accent={SECTION.members.c}>
                    <TileHeader
                      icon={<Group />}
                      title={t("teams.edit.members")}
                      subtitle={t("teams.edit.membersSubtitle") || "Pick everyone with read+write access"}
                      accent={SECTION.members.c}
                      count={(team.users || []).length}
                    />
                    <Box sx={{ p: 2 }}>
                      <PickerField
                        options={users}
                        value={team.users}
                        onChange={(v) => setTeam({ ...team, users: v })}
                        accent={SECTION.members.c}
                        label={t("teams.edit.selectUsers")}
                        placeholder={t("teams.edit.tabs.users")}
                        getOptionLabel={(o) => o.username}
                      />
                    </Box>
                  </TileCard>
                </Grid>
                <Grid item xs={12} md={6}>
                  <TileCard elevation={0} accent={SECTION.admins.c}>
                    <TileHeader
                      icon={<Star />}
                      title={t("teams.edit.admins")}
                      subtitle={t("teams.edit.adminsHelp")}
                      accent={SECTION.admins.c}
                      count={(team.admins || []).length}
                    />
                    <Box sx={{ p: 2 }}>
                      <PickerField
                        options={users}
                        value={team.admins}
                        onChange={(v) => setTeam({ ...team, admins: v })}
                        accent={SECTION.admins.c}
                        label={t("teams.edit.selectAdmins")}
                        placeholder={t("teams.edit.admins")}
                        getOptionLabel={(o) => o.username}
                      />
                    </Box>
                  </TileCard>
                </Grid>

                {!isNewTeam && (
                  <Grid item xs={12}>
                    <TileCard elevation={0} accent={ACCENT}>
                      <TileHeader
                        icon={<Send />}
                        title={t("teams.edit.invite")}
                        subtitle={t("teams.edit.inviteHelp")}
                        accent={ACCENT}
                      />
                      <Box sx={{ p: 2, display: "flex", gap: 1, alignItems: "stretch", flexWrap: "wrap" }}>
                        <TextField
                          size="small"
                          label={t("teams.edit.username")}
                          value={inviteUsername}
                          onChange={(e) => setInviteUsername(e.target.value)}
                          sx={{ ...fieldSx(ACCENT), minWidth: 280, flex: 1 }}
                        />
                        <Button
                          variant="contained"
                          startIcon={<Send />}
                          onClick={handleInvite}
                          disabled={!inviteUsername.trim()}
                          sx={{
                            textTransform: "none",
                            fontWeight: 700,
                            background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                            boxShadow: `0 4px 14px ${ACCENT}55`,
                            "&:hover": {
                              background: `linear-gradient(135deg, ${ACCENT} 0%, #86198f 100%)`,
                              boxShadow: `0 6px 18px ${ACCENT}77`,
                            },
                          }}
                        >
                          {t("teams.edit.sendInvite")}
                        </Button>
                      </Box>
                    </TileCard>
                  </Grid>
                )}
              </Grid>
            </TabPanel>

            {/* PROJECTS */}
            <TabPanel value={tabValue} index={1}>
              <TileCard elevation={0} accent={SECTION.projects.c}>
                <TileHeader
                  icon={<Workspaces />}
                  title={t("teams.edit.projectsHeading")}
                  subtitle={t("teams.edit.projectsHelp")}
                  accent={SECTION.projects.c}
                  count={(team.projects || []).length}
                />
                <Box sx={{ p: 2 }}>
                  <PickerField
                    options={projects}
                    value={team.projects}
                    onChange={(v) => setTeam({ ...team, projects: v })}
                    accent={SECTION.projects.c}
                    label={t("teams.edit.selectProjects")}
                    placeholder={t("teams.edit.tabs.projects")}
                  />
                </Box>
              </TileCard>
            </TabPanel>

            {/* MODELS */}
            <TabPanel value={tabValue} index={2}>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <TileCard elevation={0} accent={SECTION.llms.c}>
                    <TileHeader icon={<Psychology />} title={t("teams.edit.llms")} accent={SECTION.llms.c} count={(team.llms || []).length} />
                    <Box sx={{ p: 2 }}>
                      <PickerField
                        options={llms}
                        value={team.llms}
                        onChange={(v) => setTeam({ ...team, llms: v })}
                        accent={SECTION.llms.c}
                        label={t("teams.edit.selectLlms")}
                        placeholder={t("nav.llms")}
                      />
                    </Box>
                  </TileCard>
                </Grid>
                <Grid item xs={12} md={6}>
                  <TileCard elevation={0} accent={SECTION.embeddings.c}>
                    <TileHeader icon={<Psychology />} title={t("teams.edit.embeddings")} accent={SECTION.embeddings.c} count={(team.embeddings || []).length} />
                    <Box sx={{ p: 2 }}>
                      <PickerField
                        options={embeddings}
                        value={team.embeddings}
                        onChange={(v) => setTeam({ ...team, embeddings: v })}
                        accent={SECTION.embeddings.c}
                        label={t("teams.edit.selectEmbeddings")}
                        placeholder={t("nav.embeddings")}
                      />
                    </Box>
                  </TileCard>
                </Grid>
                <Grid item xs={12} md={6}>
                  <TileCard elevation={0} accent={SECTION.imageGen.c}>
                    <TileHeader icon={<Image />} title={t("teams.edit.imageGen")} accent={SECTION.imageGen.c} count={(team.image_generators || []).length} />
                    <Box sx={{ p: 2 }}>
                      {imageGenerators.length > 0 ? (
                        <PickerField
                          options={imageGenerators}
                          value={team.image_generators}
                          onChange={(v) => setTeam({ ...team, image_generators: v })}
                          accent={SECTION.imageGen.c}
                          label={t("teams.edit.selectImageGen")}
                          placeholder={t("teams.edit.imageGen")}
                          isOptionEqualToValue={(o, v) => o.name === v.name}
                        />
                      ) : (
                        <Typography variant="body2" sx={{ color: "text.disabled", fontStyle: "italic" }}>
                          {t("teams.edit.noImageGen")}
                        </Typography>
                      )}
                    </Box>
                  </TileCard>
                </Grid>
                <Grid item xs={12} md={6}>
                  <TileCard elevation={0} accent={SECTION.audioGen.c}>
                    <TileHeader icon={<Speaker />} title={t("teams.edit.audioGen")} accent={SECTION.audioGen.c} count={(team.audio_generators || []).length} />
                    <Box sx={{ p: 2 }}>
                      {audioGenerators.length > 0 ? (
                        <PickerField
                          options={audioGenerators}
                          value={team.audio_generators}
                          onChange={(v) => setTeam({ ...team, audio_generators: v })}
                          accent={SECTION.audioGen.c}
                          label={t("teams.edit.selectAudioGen")}
                          placeholder={t("teams.edit.audioGen")}
                          isOptionEqualToValue={(o, v) => o.name === v.name}
                        />
                      ) : (
                        <Typography variant="body2" sx={{ color: "text.disabled", fontStyle: "italic" }}>
                          {t("teams.edit.noAudioGen")}
                        </Typography>
                      )}
                    </Box>
                  </TileCard>
                </Grid>
              </Grid>
            </TabPanel>

            {/* BRANDING */}
            <TabPanel value={tabValue} index={3}>
              <TileCard elevation={0} accent={SECTION.branding.c}>
                <TileHeader
                  icon={<Palette />}
                  title={t("teams.edit.branding")}
                  subtitle={t("teams.edit.brandingHelp")}
                  accent={SECTION.branding.c}
                />
                <Box sx={{ p: 2.5 }}>
                  <Grid container spacing={2}>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label={t("teams.edit.appName")}
                        value={team.branding?.app_name || ""}
                        onChange={(e) => setTeam({ ...team, branding: { ...team.branding, app_name: e.target.value } })}
                        helperText={t("teams.edit.appNameHelp")}
                        sx={fieldSx(SECTION.branding.c)}
                      />
                    </Grid>
                    <Grid item xs={12} sm={6}>
                      <TextField
                        fullWidth
                        label={t("teams.edit.logoUrl")}
                        value={team.branding?.logo_url || ""}
                        onChange={(e) => setTeam({ ...team, branding: { ...team.branding, logo_url: e.target.value } })}
                        helperText={t("teams.edit.logoUrlHelp")}
                        sx={fieldSx(SECTION.branding.c)}
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
                        sx={fieldSx(SECTION.branding.c)}
                        InputProps={{
                          endAdornment: (
                            <InputAdornment position="end">
                              <Box
                                sx={{
                                  width: 28, height: 28,
                                  borderRadius: 1,
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
                        sx={fieldSx(SECTION.branding.c)}
                        InputProps={{
                          endAdornment: (
                            <InputAdornment position="end">
                              <Box
                                sx={{
                                  width: 28, height: 28,
                                  borderRadius: 1,
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
                        sx={fieldSx(SECTION.branding.c)}
                      />
                    </Grid>

                    {(team.branding?.logo_url || team.branding?.primary_color || team.branding?.app_name) && (
                      <Grid item xs={12}>
                        <Box
                          component="span"
                          sx={{
                            display: "block",
                            fontFamily: FONT_MONO,
                            fontSize: "0.62rem",
                            letterSpacing: "0.12em",
                            textTransform: "uppercase",
                            fontWeight: 700,
                            color: "text.secondary",
                            mb: 1,
                          }}
                        >
                          {t("teams.edit.preview")}
                        </Box>
                        <Box
                          sx={{
                            display: "flex",
                            alignItems: "center",
                            gap: 1.5,
                            p: 2,
                            borderRadius: 2,
                            background: team.branding?.primary_color || "#1976d2",
                            color: "#fff",
                            boxShadow: `0 8px 24px ${(team.branding?.primary_color || "#1976d2")}55`,
                            position: "relative",
                            overflow: "hidden",
                            "&::after": {
                              content: '""',
                              position: "absolute",
                              right: -40, top: -40,
                              width: 140, height: 140,
                              borderRadius: "50%",
                              background: team.branding?.secondary_color || "rgba(255,255,255,0.15)",
                              opacity: 0.25,
                            },
                          }}
                        >
                          {team.branding?.logo_url
                            ? <img width="32" height="32" src={team.branding.logo_url} alt="logo" style={{ objectFit: "contain", position: "relative", zIndex: 1 }} />
                            : <img width="32" height="32" src="/admin/assets/images/restai-logo.png" alt="logo" style={{ position: "relative", zIndex: 1 }} />}
                          <Typography variant="h6" sx={{ color: "#fff", fontWeight: 700, position: "relative", zIndex: 1 }}>
                            {team.branding?.app_name || team.name || "RESTai"}
                          </Typography>
                        </Box>
                        {team.branding?.welcome_message && (
                          <Box
                            sx={{
                              mt: 1,
                              p: 1.5,
                              borderRadius: 1.5,
                              border: `1px dashed ${SECTION.branding.c}55`,
                              backgroundColor: SECTION.branding.soft,
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
                </Box>
              </TileCard>
            </TabPanel>

            {/* INTEGRATIONS */}
            <TabPanel value={tabValue} index={4}>
              <TileCard elevation={0} accent={SECTION.integrations.c}>
                <TileHeader
                  icon={<Mail />}
                  title={t("teams.edit.email.title") || "Email (SMTP)"}
                  subtitle={t("teams.edit.email.subtitle") || "Empty fields fall back to platform Notifications settings."}
                  accent={SECTION.integrations.c}
                />
                <Box sx={{ p: 3 }}>
                  <Grid container spacing={3}>
                    <Grid item xs={12} md={8}>
                      <TextField
                        fullWidth
                        label={t("settings.fields.smtpHost")}
                        placeholder="smtp.example.com"
                        value={team.options?.smtp_host || ""}
                        onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_host: e.target.value } })}
                        sx={fieldSx(SECTION.integrations.c)}
                      />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField
                        fullWidth
                        label={t("settings.fields.smtpPort")}
                        placeholder="587"
                        value={team.options?.smtp_port || ""}
                        onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_port: e.target.value } })}
                        sx={fieldSx(SECTION.integrations.c)}
                      />
                    </Grid>
                    <Grid item xs={12} md={2}>
                      <TextField
                        fullWidth
                        label={t("settings.fields.emailDefaultTo")}
                        value={team.options?.email_default_to || ""}
                        onChange={(e) => setTeam({ ...team, options: { ...team.options, email_default_to: e.target.value } })}
                        sx={fieldSx(SECTION.integrations.c)}
                      />
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label={t("settings.fields.smtpUser")}
                        value={team.options?.smtp_user || ""}
                        onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_user: e.target.value } })}
                        sx={fieldSx(SECTION.integrations.c)}
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
                        sx={fieldSx(SECTION.integrations.c)}
                      />
                    </Grid>
                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label={t("settings.fields.smtpFrom")}
                        placeholder='"Team Bot" <bot@example.com>'
                        value={team.options?.smtp_from || ""}
                        onChange={(e) => setTeam({ ...team, options: { ...team.options, smtp_from: e.target.value } })}
                        sx={fieldSx(SECTION.integrations.c)}
                      />
                    </Grid>
                  </Grid>
                </Box>
              </TileCard>
            </TabPanel>
          </TileCard>
        </Box>

        {/* Sticky-ish bottom save bar (mirrors the hero actions for long forms) */}
        <Box
          sx={{
            mt: 2.5,
            display: "flex",
            justifyContent: "flex-end",
            gap: 1,
          }}
        >
          <Button
            variant="outlined"
            startIcon={<Close />}
            onClick={handleCancel}
            sx={{
              textTransform: "none",
              color: "text.secondary",
              borderColor: "rgba(15,23,42,0.15)",
              "&:hover": { borderColor: "rgba(15,23,42,0.4)", backgroundColor: "rgba(15,23,42,0.03)" },
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
              fontWeight: 700,
              background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
              boxShadow: `0 4px 14px ${ACCENT}55`,
              "&:hover": {
                background: `linear-gradient(135deg, ${ACCENT} 0%, #86198f 100%)`,
                boxShadow: `0 6px 18px ${ACCENT}77`,
              },
            }}
          >
            {saving
              ? t("common.saving") || "Saving…"
              : isNewTeam ? t("teams.edit.createTeam") : t("teams.edit.saveChanges")}
          </Button>
        </Box>
      </form>
    </Container>
  );
}
