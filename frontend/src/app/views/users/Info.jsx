import { useState, useEffect, Fragment } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import sha256 from "crypto-js/sha256";

import {
  Box,
  Card,
  Chip,
  Grid,
  styled,
  Drawer,
  Button,
  IconButton,
  Tooltip,
  Typography,
  useMediaQuery,
} from "@mui/material";

import { H5 } from "app/components/Typography";
import { FlexBox } from "app/components/FlexBox";
import { ContentCopy, PersonOutline, Edit, Delete } from "@mui/icons-material";

import ApiKeys from "./components/ApiKeys";
import Password from "./components/Password";
import Projects from "./components/Projects";
import Teams from "./components/Teams";
import UserActivity from "./components/UserActivity";
import DeleteAccount from "./components/DeleteAccount";
import TwoFactorAuth from "./components/TwoFactorAuth";
import BasicInformation from "./components/BasicInformation";
import api from "app/utils/api";
import InfoIcon from "@mui/icons-material/Info";
import KeyIcon from "@mui/icons-material/Key";
import HttpsIcon from "@mui/icons-material/Https";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import TimelineIcon from "@mui/icons-material/Timeline";
import SecurityIcon from "@mui/icons-material/Security";
import GroupsIcon from "@mui/icons-material/Groups";
import { shimmer, sweep, blink } from "app/components/page/pageStyles";

const StyledButton = styled(Button)(({ theme }) => ({
  borderRadius: 0,
  overflow: "hidden",
  position: "relative",
  whiteSpace: "nowrap",
  textOverflow: "ellipsis",
  padding: "0.7rem 1.25rem",
  justifyContent: "flex-start",
  color: theme.palette.text.secondary,
  fontSize: "0.85rem",
  fontWeight: 500,
  textTransform: "none",
  letterSpacing: 0,
  transition: "all 0.2s ease",
  borderBottom: `1px solid ${theme.palette.divider}`,
  "&:last-of-type": { borderBottom: "none" },
}));

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Navy/cyan gradient hero — same family as ProjectInfo + AIHero. Lifts
// the user identity (avatar, name, role/auth pills, projects count)
// out of the BasicInformation tab so the page leads with a strong
// visual identity instead of a breadcrumb + duplicate avatar block.
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

  const tabList = [
    { id: "basic", name: t("users.tabs.basic"), Icon: InfoIcon },
    { id: "password", name: t("users.tabs.password"), Icon: HttpsIcon },
    { id: "twoFactor", name: t("users.tabs.twoFactor"), Icon: SecurityIcon },
    { id: "projects", name: t("users.tabs.projects"), Icon: ContentCopy },
    { id: "teams", name: t("users.tabs.teams"), Icon: GroupsIcon },
    { id: "apiKeys", name: t("users.tabs.apiKeys"), Icon: KeyIcon },
    { id: "activity", name: t("users.tabs.activity"), Icon: TimelineIcon },
    { id: "delete", name: t("users.tabs.delete"), Icon: DeleteForeverIcon }
  ];

  const activeStyle = (theme) => ({
    color: theme.palette.primary.main,
    backgroundColor: theme.palette.action.selected,
    "&::before": {
      left: 0,
      width: 3,
      content: '""',
      height: "100%",
      position: "absolute",
      transition: "all 0.3s",
      backgroundColor: theme.palette.primary.main,
    },
  });
  const hoverStyle = (theme) => ({
    color: theme.palette.text.primary,
    backgroundColor: theme.palette.action.hover,
  });

  function TabListContent() {
    return (
      <FlexBox flexDirection="column">
        {tabList.map(({ id: tabId, name, Icon }) => (
          <StyledButton
            key={tabId}
            startIcon={<Icon sx={{ fontSize: 18 }} />}
            sx={(theme) =>
              active === tabId ? activeStyle(theme) : { "&:hover": hoverStyle(theme) }
            }
            onClick={() => {
              setActive(tabId);
              setOpenDrawer(false);
            }}>
            {name}
          </StyledButton>
        ))}
      </FlexBox>
    );
  }

  const fetchUser = (username) => {
    return api.get("/users/" + username, auth.user.token)
      .then((d) => {
        setUser(d)
        return d
      })
      .catch(() => {});
  }

  const fetchProjects = () => {
    return api.get("/projects", auth.user.token)
      .then((d) => {
        setProjects(d.projects)
      })
      .catch(() => {});
  }

  const fetchInfo = () => {
    return api.get("/info", auth.user.token)
      .then((d) => setInfo(d))
      .catch(() => {});
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - User - ' + id;
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

  const handleDelete = () => {
    if (!user.username) return;
    if (!window.confirm(`Delete user "${user.username}"?`)) return;
    api.delete("/users/" + user.username, auth.user.token)
      .then(() => navigate("/users"))
      .catch(() => {});
  };

  return (
    <Container>
      <HeroCard elevation={0}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2.5, flexWrap: "wrap" }}>
          <Box
            sx={{
              width: 76,
              height: 76,
              flexShrink: 0,
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
                src={`https://www.gravatar.com/avatar/${sha256(user.username).toString()}?d=wavatar`}
                alt={user.username}
                sx={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            )}
          </Box>

          <Box sx={{ flex: 1, minWidth: 220 }}>
            {/* Inline path trail — same pattern as the project hero. */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 0.75,
                fontFamily: '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace',
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

      <Box>
        <Grid container spacing={3}>
          <Grid item md={3} xs={12}>
            {downMd ? (
              <Fragment>
                <FlexBox alignItems="center" gap={1}>
                  <IconButton sx={{ padding: 0 }} onClick={() => setOpenDrawer(true)}>
                    <ContentCopy sx={{ color: "primary.main" }} />
                  </IconButton>

                  <H5>{t("users.showMore")}</H5>
                </FlexBox>

                <Drawer open={openDrawer} onClose={() => setOpenDrawer(false)}>
                  <Box padding={1} sx={{ minWidth: 240 }}>
                    <TabListContent />
                  </Box>
                </Drawer>
              </Fragment>
            ) : (
              <Card
                elevation={0}
                sx={{
                  py: 0.5,
                  borderRadius: 3,
                  border: "1px solid",
                  borderColor: "divider",
                  backgroundColor: "background.paper",
                  overflow: "hidden",
                }}
              >
                <TabListContent />
              </Card>
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
      </Box>
    </Container>
  );
}
