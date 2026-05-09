import { useState, useEffect, Fragment } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import sha256 from "crypto-js/sha256";

import {
  Box,
  Card,
  Chip,
  Drawer,
  Grid,
  IconButton,
  Tooltip,
  Typography,
  styled,
  useMediaQuery,
} from "@mui/material";

import {
  PersonOutline, Edit, Delete, Menu as MenuIcon,
  Info as InfoIcon, Key as KeyIcon, Https as HttpsIcon,
  DeleteForever as DeleteForeverIcon, Timeline as TimelineIcon,
  Security as SecurityIcon, Groups as GroupsIcon, Workspaces,
} from "@mui/icons-material";

import ApiKeys from "./components/ApiKeys";
import Password from "./components/Password";
import Projects from "./components/Projects";
import Teams from "./components/Teams";
import UserActivity from "./components/UserActivity";
import DeleteAccount from "./components/DeleteAccount";
import TwoFactorAuth from "./components/TwoFactorAuth";
import BasicInformation from "./components/BasicInformation";
import api from "app/utils/api";
import { FONT_MONO, shimmer, sweep, blink } from "app/components/page/pageStyles";

const ACCENT = "#4338ca";        // indigo-700, matches Users list page
const ACCENT_SOFT = "rgba(67,56,202,0.10)";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Same navy/cyan hero as ProjectInfo / TeamView so the landing pages
// stay one family.
const HeroCard = styled(Card)(({ theme }) => ({
  position: "relative",
  padding: theme.spacing(4),
  marginBottom: theme.spacing(3),
  borderRadius: 20,
  overflow: "hidden",
  color: "#fff",
  background: `
    radial-gradient(at 20% 20%, rgba(25,118,210,0.95) 0px, transparent 55%),
    radial-gradient(at 85% 15%, rgba(14,165,233,0.90) 0px, transparent 55%),
    radial-gradient(at 75% 85%, rgba(6,182,212,0.80) 0px, transparent 55%),
    radial-gradient(at 10% 90%, rgba(56,189,248,0.70) 0px, transparent 55%),
    linear-gradient(135deg, #0b1d3a 0%, #0f2c5a 100%)
  `,
  backgroundSize: "200% 200%, 200% 200%, 200% 200%, 200% 200%, 100% 100%",
  animation: `${shimmer} 20s ease-in-out infinite`,
  [theme.breakpoints.down("md")]: { padding: theme.spacing(3) },
  "&::after": {
    content: '""',
    position: "absolute",
    inset: 0,
    pointerEvents: "none",
    backgroundImage:
      "radial-gradient(rgba(255,255,255,0.04) 1px, transparent 1px)",
    backgroundSize: "4px 4px",
    mixBlendMode: "overlay",
    opacity: 0.5,
  },
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 2,
    background:
      "linear-gradient(90deg, transparent, rgba(125,211,252,0.55), rgba(56,189,248,0.55), transparent)",
    animation: `${sweep} 6s ease-in-out infinite`,
    pointerEvents: "none",
    zIndex: 2,
  },
  "& > *": { position: "relative", zIndex: 1 },
}));

const ActionBar = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(0.75),
  flexWrap: "wrap",
  marginTop: theme.spacing(3),
  paddingTop: theme.spacing(2),
  borderTop: "1px solid rgba(255,255,255,0.12)",
}));

const pillSx = {
  backgroundColor: "rgba(255,255,255,0.08)",
  border: "1px solid rgba(255,255,255,0.18)",
  color: "rgba(255,255,255,0.92)",
  backdropFilter: "blur(12px)",
  fontWeight: 500,
  "& .MuiChip-icon": { color: "rgba(255,255,255,0.85)" },
};
const pillAdminSx = {
  ...pillSx,
  backgroundColor: "rgba(239,68,68,0.20)",
  border: "1px solid rgba(252,165,165,0.5)",
  color: "#fecaca",
  "& .MuiChip-icon": { color: "#fecaca" },
};
const pillWarnSx = {
  ...pillSx,
  backgroundColor: "rgba(245,158,11,0.18)",
  border: "1px solid rgba(245,158,11,0.5)",
  color: "#fde68a",
  "& .MuiChip-icon": { color: "#fde68a" },
};
const pillInfoSx = {
  ...pillSx,
  backgroundColor: "rgba(56,189,248,0.18)",
  border: "1px solid rgba(56,189,248,0.5)",
  color: "#bae6fd",
  "& .MuiChip-icon": { color: "#bae6fd" },
};

const heroIconBtnSx = {
  color: "rgba(255,255,255,0.85)",
  border: "1px solid rgba(255,255,255,0.16)",
  borderRadius: 1.5,
  background: "rgba(255,255,255,0.06)",
  backdropFilter: "blur(12px)",
  transition: "all 0.2s ease",
  "&:hover": {
    color: "#fff",
    background: "rgba(255,255,255,0.14)",
    borderColor: "rgba(255,255,255,0.32)",
  },
};
const heroIconBtnDangerSx = {
  ...heroIconBtnSx,
  color: "#fca5a5",
  "&:hover": {
    color: "#fff",
    background: "rgba(239,68,68,0.32)",
    borderColor: "rgba(252,165,165,0.6)",
  },
};

// ── Tab nav sidebar — modernised. Section labels in mono, items with
// indigo rail on active, sky-tinted on hover. Matches the ProjectTabNav
// vocabulary but adapted to the user-info structure.
const NavCard = styled(Card)(() => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: ACCENT,
    opacity: 0.85,
    pointerEvents: "none",
  },
}));

const NavSectionLabel = styled("div")(() => ({
  display: "flex",
  alignItems: "center",
  gap: 8,
  paddingLeft: 14,
  paddingRight: 14,
  marginTop: 14,
  marginBottom: 4,
  "&::before": {
    content: '""',
    width: 10,
    height: 2,
    background: ACCENT,
    flexShrink: 0,
  },
  "& > span": {
    fontFamily: FONT_MONO,
    fontSize: 10,
    letterSpacing: "0.14em",
    textTransform: "uppercase",
    fontWeight: 800,
    color: "text.secondary",
  },
}));

const NavItem = styled("button", {
  shouldForwardProp: (p) => p !== "active" && p !== "danger",
})(({ active, danger }) => ({
  position: "relative",
  display: "flex",
  alignItems: "center",
  gap: 10,
  width: "calc(100% - 12px)",
  marginLeft: 6,
  marginRight: 6,
  marginBottom: 2,
  height: 36,
  paddingLeft: 14,
  paddingRight: 14,
  border: "none",
  borderRadius: 6,
  backgroundColor: active
    ? (danger ? "rgba(239,68,68,0.10)" : ACCENT_SOFT)
    : "transparent",
  color: active
    ? (danger ? "#dc2626" : ACCENT)
    : "rgba(15,23,42,0.78)",
  cursor: "pointer",
  fontSize: "0.84rem",
  fontWeight: active ? 700 : 500,
  textAlign: "left",
  transition: "all 160ms cubic-bezier(0.4, 0, 0.2, 1)",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, top: 0, bottom: 0,
    width: 3,
    background: danger ? "#dc2626" : ACCENT,
    opacity: active ? 1 : 0,
    transform: active ? "scaleY(1)" : "scaleY(0.6)",
    transition: "opacity 160ms, transform 160ms",
  },
  "&:hover": {
    backgroundColor: active
      ? (danger ? "rgba(239,68,68,0.12)" : ACCENT_SOFT)
      : (danger ? "rgba(239,68,68,0.05)" : "rgba(15,23,42,0.04)"),
    color: danger ? "#dc2626" : ACCENT,
    "&::before": { opacity: 0.6, transform: "scaleY(1)" },
    "& .nav-icon": { color: danger ? "#dc2626" : ACCENT },
  },
  "& .nav-icon": {
    fontSize: 17,
    flexShrink: 0,
    transition: "color 160ms",
    color: active ? (danger ? "#dc2626" : ACCENT) : "rgba(15,23,42,0.55)",
  },
}));

// Stat tile — mono, sky-line, no card chrome (just lives inside the
// nav card under the header).
function MiniStat({ icon: Icon, label, value, color = ACCENT }) {
  return (
    <Box
      sx={{
        display: "flex",
        alignItems: "center",
        gap: 1,
        px: 1.75, py: 0.75,
      }}
    >
      <Icon sx={{ fontSize: 14, color, opacity: 0.75 }} />
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.6rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: "text.secondary",
          fontWeight: 700,
          flex: 1,
        }}
      >
        {label}
      </Box>
      <Box
        component="span"
        sx={{
          fontFamily: FONT_MONO,
          fontSize: "0.78rem",
          fontWeight: 800,
          color,
        }}
      >
        {value}
      </Box>
    </Box>
  );
}

export default function UserInfo() {
  const { t } = useTranslation();
  const { id } = useParams();
  const navigate = useNavigate();
  const [projects, setProjects] = useState([]);
  const [user, setUser] = useState({});
  // eslint-disable-next-line no-unused-vars
  const [info, setInfo] = useState({ "version": "", "embeddings": [], "llms": [], "loaders": [] });
  const auth = useAuth();
  const [openDrawer, setOpenDrawer] = useState(false);
  const [active, setActive] = useState("basic");
  const downMd = useMediaQuery((theme) => theme.breakpoints.down("md"));

  const tabSections = [
    {
      label: t("users.tabs.account") || "Account",
      items: [
        { id: "basic", name: t("users.tabs.basic"), Icon: InfoIcon },
        { id: "password", name: t("users.tabs.password"), Icon: HttpsIcon },
        { id: "twoFactor", name: t("users.tabs.twoFactor"), Icon: SecurityIcon },
        { id: "apiKeys", name: t("users.tabs.apiKeys"), Icon: KeyIcon },
      ],
    },
    {
      label: t("users.tabs.access") || "Access",
      items: [
        { id: "projects", name: t("users.tabs.projects"), Icon: Workspaces },
        { id: "teams", name: t("users.tabs.teams"), Icon: GroupsIcon },
      ],
    },
    {
      label: t("users.tabs.history") || "History",
      items: [
        { id: "activity", name: t("users.tabs.activity"), Icon: TimelineIcon },
      ],
    },
    {
      label: t("users.tabs.dangerZone") || "Danger zone",
      items: [
        { id: "delete", name: t("users.tabs.delete"), Icon: DeleteForeverIcon, danger: true },
      ],
    },
  ];

  function TabListContent() {
    return (
      <Box sx={{ pb: 2 }}>
        {tabSections.map((section) => (
          <Box key={section.label}>
            <NavSectionLabel>
              <span>{section.label}</span>
            </NavSectionLabel>
            {section.items.map(({ id: tabId, name, Icon, danger }) => (
              <NavItem
                key={tabId}
                active={active === tabId}
                danger={danger}
                onClick={() => {
                  setActive(tabId);
                  setOpenDrawer(false);
                }}
              >
                <Icon className="nav-icon" />
                <Box component="span">{name}</Box>
              </NavItem>
            ))}
          </Box>
        ))}
      </Box>
    );
  }

  const fetchUser = (username) => {
    return api.get("/users/" + username, auth.user.token)
      .then((d) => { setUser(d); return d; })
      .catch(() => {});
  };

  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => setProjects(d.projects))
      .catch(() => {});
  };

  const fetchInfo = () => {
    return api.get("/info", auth.user.token)
      .then(setInfo)
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - User - " + id;
    fetchUser(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    fetchProjects();
    fetchInfo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isViewingSelf = user.username && user.username === auth.user?.username;
  const canImpersonate = auth.user?.is_admin && user.username && !isViewingSelf;
  const canDelete = auth.user?.is_admin && !isViewingSelf;
  const projectCount = (user.projects || []).length;
  const teamCount = (user.teams || []).length;
  const apiKeyCount = (user.api_keys || []).length;

  const handleDelete = () => {
    if (!user.username) return;
    if (!window.confirm(`Delete user "${user.username}"?`)) return;
    api.delete("/users/" + user.username, auth.user.token)
      .then(() => navigate("/users"))
      .catch(() => {});
  };

  return (
    <Container>
      {/* ── HERO ──────────────────────────────────────────────── */}
      <HeroCard elevation={0}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2.5, flexWrap: "wrap" }}>
          <Box
            sx={{
              width: 76, height: 76, flexShrink: 0,
              borderRadius: "50%",
              border: "2px solid rgba(255,255,255,0.25)",
              overflow: "hidden",
              background: "rgba(255,255,255,0.08)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 8px 24px rgba(0,0,0,0.25)",
            }}
          >
            {user.username && (
              <Box
                component="img"
                src={`https://www.gravatar.com/avatar/${sha256(user.username).toString()}?d=identicon`}
                alt={user.username}
                sx={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            )}
          </Box>

          <Box sx={{ flex: 1, minWidth: 220 }}>
            {/* Inline path trail */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.75,
                fontFamily: FONT_MONO,
                fontSize: "0.65rem",
                letterSpacing: 3,
                lineHeight: 1.2,
                textTransform: "uppercase",
              }}
            >
              <Box
                component="span"
                role="link"
                tabIndex={0}
                onClick={() => navigate("/users")}
                onKeyDown={(e) => { if (e.key === "Enter") navigate("/users"); }}
                sx={{
                  color: "rgba(255,255,255,0.75)",
                  cursor: "pointer",
                  transition: "color 0.15s ease",
                  "&:hover": {
                    color: "#fff",
                    textDecoration: "underline",
                    textUnderlineOffset: "3px",
                  },
                }}
              >
                Users
              </Box>
              <Box component="span" sx={{ color: "rgba(255,255,255,0.4)" }}>/</Box>
              <Box component="span" sx={{ color: "rgba(125,211,252,0.95)" }}>
                {user.username || id}
              </Box>
            </Box>

            <Typography
              variant="h4"
              sx={{
                mt: 0.5,
                fontWeight: 700,
                color: "#fff",
                letterSpacing: "-0.5px",
                textShadow: "0 2px 20px rgba(0,0,0,0.2)",
              }}
            >
              {user.username || id}
              <Box
                component="span"
                sx={{
                  display: "inline-block",
                  width: 10,
                  ml: 0.5,
                  animation: `${blink} 1.1s steps(2, start) infinite`,
                  color: "rgba(125,211,252,0.9)",
                }}
              >_</Box>
            </Typography>

            {user.email && (
              <Typography
                variant="body2"
                sx={{ mt: 0.75, color: "rgba(255,255,255,0.78)" }}
              >
                {user.email}
              </Typography>
            )}

            {/* Metadata pills */}
            <Box sx={{ display: "flex", gap: 1, mt: 2, flexWrap: "wrap", alignItems: "center" }}>
              <Chip
                size="small"
                label={user.is_admin ? t("users.basic.roleAdmin") || "Admin" : t("users.basic.roleRegular") || "User"}
                sx={user.is_admin ? pillAdminSx : pillSx}
              />
              <Chip
                size="small"
                label={user.sso ? (t("users.basic.authSso") || "SSO") : (t("users.basic.authLocal") || "Local")}
                sx={pillSx}
              />
              {user.is_restricted && (
                <Chip size="small" label="Read-only" sx={pillWarnSx} />
              )}
              {projectCount > 0 && (
                <Chip size="small" label={`${projectCount} ${t("users.basic.projects") || "projects"}`} sx={pillInfoSx} />
              )}
              {teamCount > 0 && (
                <Chip size="small" label={`${teamCount} teams`} sx={pillInfoSx} />
              )}
              {isViewingSelf && (
                <Chip size="small" label={t("users.basic.you") || "You"} sx={pillInfoSx} />
              )}
            </Box>
          </Box>
        </Box>

        <ActionBar>
          {canImpersonate && (
            <Tooltip title={t("users.basic.impersonate")}>
              <IconButton
                size="small"
                sx={heroIconBtnSx}
                onClick={() => auth.impersonate(user.username)}
              >
                <PersonOutline fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          {auth.user?.is_admin && (
            <Tooltip title={t("common.edit") || "Edit"}>
              <IconButton
                size="small"
                sx={heroIconBtnSx}
                onClick={() => setActive("basic")}
              >
                <Edit fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Box sx={{ flex: 1 }} />
          {canDelete && (
            <Tooltip title={t("common.delete") || "Delete"}>
              <IconButton
                size="small"
                sx={heroIconBtnDangerSx}
                onClick={handleDelete}
              >
                <Delete fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
        </ActionBar>
      </HeroCard>

      {/* ── BODY: nav sidebar + content panel ────────────────── */}
      <Grid container spacing={3}>
        <Grid item md={3} xs={12}>
          {downMd ? (
            <Fragment>
              <NavCard sx={{ p: 1.25 }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  <IconButton
                    size="small"
                    onClick={() => setOpenDrawer(true)}
                    sx={{ color: ACCENT }}
                  >
                    <MenuIcon />
                  </IconButton>
                  <Box
                    component="span"
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.7rem",
                      letterSpacing: "0.1em",
                      textTransform: "uppercase",
                      fontWeight: 800,
                      color: ACCENT,
                    }}
                  >
                    {t("users.showMore")}
                  </Box>
                </Box>
              </NavCard>
              <Drawer open={openDrawer} onClose={() => setOpenDrawer(false)}>
                <Box sx={{ minWidth: 260, background: "#fff", height: "100%" }}>
                  <TabListContent />
                </Box>
              </Drawer>
            </Fragment>
          ) : (
            <NavCard elevation={0}>
              {/* Mini stats inside the nav card — keeps the page tight */}
              <Box sx={{ pt: 2, pb: 1, borderBottom: "1px dashed rgba(15,23,42,0.06)" }}>
                <MiniStat icon={Workspaces} label="Projects" value={projectCount} color={ACCENT} />
                <MiniStat icon={GroupsIcon} label="Teams" value={teamCount} color="#0891b2" />
                {apiKeyCount > 0 && (
                  <MiniStat icon={KeyIcon} label="Keys" value={apiKeyCount} color="#7c3aed" />
                )}
              </Box>
              <TabListContent />
            </NavCard>
          )}
        </Grid>

        <Grid item md={9} xs={12}>
          {active === "basic" && <BasicInformation user={user} />}
          {active === "password" && <Password user={user} />}
          {active === "twoFactor" && <TwoFactorAuth user={user} />}
          {active === "projects" && <Projects user={user} projects={projects} />}
          {active === "teams" && <Teams user={user} />}
          {active === "apiKeys" && <ApiKeys user={user} />}
          {active === "activity" && user.id && <UserActivity user={user} />}
          {active === "delete" && <DeleteAccount user={user} />}
        </Grid>
      </Grid>
    </Container>
  );
}
