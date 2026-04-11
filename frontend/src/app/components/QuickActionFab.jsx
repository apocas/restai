import { useMemo } from "react";
import { SpeedDial, SpeedDialAction, SpeedDialIcon, styled, useMediaQuery, useTheme } from "@mui/material";
import {
  Assignment, Psychology, Hub, Person, Groups,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";

const StyledSpeedDial = styled(SpeedDial)(({ theme }) => ({
  position: "fixed",
  bottom: theme.spacing(3),
  right: theme.spacing(3),
  zIndex: theme.zIndex.speedDial,
  "& .MuiFab-primary": {
    width: 56,
    height: 56,
    boxShadow: "0 8px 24px -6px rgba(99,102,241,0.45)",
  },
  "& .MuiSpeedDialAction-staticTooltipLabel": {
    width: 150,
    maxWidth: "none",
    textAlign: "center",
    whiteSpace: "nowrap",
    fontWeight: 500,
  },
}));

export default function QuickActionFab() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("sm"));

  const actions = useMemo(() => {
    if (!user || user.is_restricted) return [];
    const items = [
      { icon: <Assignment />, name: "New Project", path: "/projects/new" },
    ];
    if (user.is_admin) {
      items.push(
        { icon: <Psychology />, name: "New LLM", path: "/llms/new" },
        { icon: <Hub />, name: "New Embedding", path: "/embeddings/new" },
        { icon: <Person />, name: "New User", path: "/users/new" },
        { icon: <Groups />, name: "New Team", path: "/teams/new" },
      );
    }
    return items;
  }, [user]);

  if (actions.length === 0 || isMobile) return null;

  // If there's only one action, clicking the FAB goes directly to it
  if (actions.length === 1) {
    return (
      <StyledSpeedDial
        ariaLabel="Quick create"
        icon={<SpeedDialIcon />}
        onClick={() => navigate(actions[0].path)}
        open={false}
      />
    );
  }

  return (
    <StyledSpeedDial
      ariaLabel="Quick create"
      icon={<SpeedDialIcon />}
      FabProps={{ color: "primary" }}
    >
      {actions.map((action) => (
        <SpeedDialAction
          key={action.name}
          icon={action.icon}
          tooltipTitle={action.name}
          tooltipOpen
          onClick={() => navigate(action.path)}
        />
      ))}
    </StyledSpeedDial>
  );
}
