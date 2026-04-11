import { memo, useState, useEffect } from "react";
import { Link } from "react-router-dom";
import {
  Badge,
  Box,
  styled,
  Avatar,
  Hidden,
  useTheme,
  MenuItem,
  IconButton,
  useMediaQuery
} from "@mui/material";

import useAuth from "app/hooks/useAuth";
import useSettings from "app/hooks/useSettings";
import api from "app/utils/api";

import { Span } from "app/components/Typography";
import { MatxMenu } from "app/components";
import { themeShadows } from "app/components/MatxTheme/themeColors";

import { topBarHeight } from "app/utils/constant";

import sha256 from 'crypto-js/sha256';

import {
  Home,
  Mail,
  Menu,
  Person,
  PowerSettingsNew,
  Search as SearchIcon,
} from "@mui/icons-material";
import SmartSearch from "app/components/SmartSearch";

const StyledIconButton = styled(IconButton)(({ theme }) => ({
  color: theme.palette.text.primary
}));

const TopbarRoot = styled("div")({
  top: 0,
  zIndex: 96,
  height: topBarHeight,
  boxShadow: themeShadows[8],
  transition: "all 0.3s ease"
});

const TopbarContainer = styled(Box)(({ theme }) => ({
  padding: "8px",
  paddingLeft: 18,
  paddingRight: 20,
  height: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  background: theme.palette.primary.main,
  [theme.breakpoints.down("sm")]: { paddingLeft: 16, paddingRight: 16 },
  [theme.breakpoints.down("xs")]: { paddingLeft: 14, paddingRight: 16 }
}));

const UserMenu = styled(Box)({
  padding: 4,
  display: "flex",
  borderRadius: 24,
  cursor: "pointer",
  alignItems: "center",
  "& span": { margin: "0 8px" }
});

const StyledItem = styled(MenuItem)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  minWidth: 185,
  "& a": {
    width: "100%",
    display: "flex",
    alignItems: "center",
    textDecoration: "none"
  },
  "& > svg, & a > svg, & a > .MuiBadge-root": { marginRight: 12 },
  "& span": { color: theme.palette.text.primary }
}));


const Layout1Topbar = () => {
  const theme = useTheme();
  const { settings, updateSettings } = useSettings();
  const { logout, user } = useAuth();
  const isMdScreen = useMediaQuery(theme.breakpoints.down("md"));
  const [inviteCount, setInviteCount] = useState(0);
  const [searchOpen, setSearchOpen] = useState(false);
  const [systemLlmConfigured, setSystemLlmConfigured] = useState(false);

  const refreshInviteCount = () => {
    if (user?.token || user?.username) {
      api.get("/invitations/count", user.token, { silent: true })
        .then((data) => setInviteCount(data.count || 0))
        .catch(() => {});
    }
  };

  useEffect(() => {
    refreshInviteCount();
    window.addEventListener("invitations-changed", refreshInviteCount);
    return () => window.removeEventListener("invitations-changed", refreshInviteCount);
  }, [user?.username]);

  useEffect(() => {
    if (!user) return;
    api.get("/info", user.token, { silent: true })
      .then((d) => setSystemLlmConfigured(!!d?.system_llm_configured))
      .catch(() => {});
  }, [user?.username]);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        if (systemLlmConfigured) setSearchOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [systemLlmConfigured]);

  const updateSidebarMode = (sidebarSettings) => {
    updateSettings({ layout1Settings: { leftSidebar: { ...sidebarSettings } } });
  };

  const handleSidebarToggle = () => {
    let { layout1Settings } = settings;
    let mode;
    if (isMdScreen) {
      mode = layout1Settings.leftSidebar.mode === "close" ? "mobile" : "close";
    } else {
      mode = layout1Settings.leftSidebar.mode === "full" ? "close" : "full";
    }
    updateSidebarMode({ mode });
  };

  return (
    <TopbarRoot>
      <TopbarContainer>
        <Box display="flex">
          <StyledIconButton onClick={handleSidebarToggle}>
            <Menu />
          </StyledIconButton>
        </Box>

        <Box display="flex" alignItems="center">
          {systemLlmConfigured && (
            <StyledIconButton onClick={() => setSearchOpen(true)} title="Smart search (⌘K)">
              <SearchIcon />
            </StyledIconButton>
          )}
          <MatxMenu
            menuButton={
              <UserMenu>
                <Hidden xsDown>
                  <Span>
                    Hi <strong>{user.username}</strong>
                  </Span>
                </Hidden>
                <Badge badgeContent={inviteCount} color="error" overlap="circular">
                  <Avatar src={"https://www.gravatar.com/avatar/" + sha256(user.username)} sx={{ cursor: "pointer" }} />
                </Badge>
              </UserMenu>
            }>
            <StyledItem>
              <Link to="/">
                <Home />
                <Span>Home</Span>
              </Link>
            </StyledItem>

            <StyledItem>
              <Link to={"/user/" + user.username}>
                <Person />
                <Span>Profile</Span>
              </Link>
            </StyledItem>

            <StyledItem>
              <Link to="/invitations">
                <Badge badgeContent={inviteCount} color="error">
                  <Mail />
                </Badge>
                <Span>Invites</Span>
              </Link>
            </StyledItem>

            <StyledItem onClick={logout}>
              <PowerSettingsNew />
              <Span>Logout</Span>
            </StyledItem>
          </MatxMenu>
        </Box>
      </TopbarContainer>
      {systemLlmConfigured && (
        <SmartSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
      )}
    </TopbarRoot>
  );
};

export default memo(Layout1Topbar);
