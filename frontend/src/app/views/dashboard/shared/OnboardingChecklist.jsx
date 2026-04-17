import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Button, Card, IconButton, Stack, Typography, useTheme,
  LinearProgress, Tooltip,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import CloseIcon from "@mui/icons-material/Close";
import PsychologyIcon from "@mui/icons-material/Psychology";
import AssignmentIcon from "@mui/icons-material/Assignment";
import GroupsIcon from "@mui/icons-material/Groups";

import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";

const DISMISS_KEY = "restai_onboarding_dismissed";

export default function OnboardingChecklist() {
  const auth = useAuth();
  const navigate = useNavigate();
  const theme = useTheme();
  const [llmCount, setLlmCount] = useState(null);
  const [projects, setProjects] = useState(null);
  const [teams, setTeams] = useState(null);
  const [dismissed, setDismissed] = useState(() => {
    try { return localStorage.getItem(DISMISS_KEY) === "1"; } catch { return false; }
  });

  // Only show to admins — onboarding tasks require admin permission
  const isAdmin = auth?.user?.is_admin;

  useEffect(() => {
    if (!isAdmin || dismissed) return;

    const token = auth.user.token;
    api.get("/llms", token, { silent: true })
      .then((d) => setLlmCount(Array.isArray(d) ? d.length : (d?.llms || []).length))
      .catch(() => setLlmCount(0));

    api.get("/projects", token, { silent: true })
      .then((d) => setProjects(d?.projects || []))
      .catch(() => setProjects([]));

    api.get("/teams", token, { silent: true })
      .then((d) => setTeams(d?.teams || []))
      .catch(() => setTeams([]));
  }, [isAdmin, dismissed]);

  const steps = useMemo(() => {
    const firstTeamId = teams && teams.length > 0 ? teams[0].id : null;
    const hasLlmInTeam = (teams || []).some((t) => (t.llms || []).length > 0);
    return [
      {
        key: "llm",
        title: "Add an LLM",
        description: "Configure your first AI provider (OpenAI, Anthropic, Ollama, …) so projects can call models.",
        icon: <PsychologyIcon />,
        done: llmCount !== null && llmCount > 0,
        action: () => navigate("/llms/new"),
        cta: "Add LLM",
      },
      {
        key: "team_llm",
        title: "Add the LLM to a team",
        description: "Attach the LLM to a team so projects in that team can use it. The Default Team is created on install.",
        icon: <GroupsIcon />,
        done: hasLlmInTeam,
        action: firstTeamId
          ? () => navigate(`/team/${firstTeamId}/edit`)
          : () => navigate("/teams/new"),
        cta: firstTeamId ? "Edit Team" : "Create Team",
      },
      {
        key: "project",
        title: "Create your first project",
        description: "Pick a type — RAG, agent, or block — and configure it. The playground is the fastest way to test.",
        icon: <AssignmentIcon />,
        done: projects !== null && projects.length > 0,
        action: () => navigate("/projects/new"),
        cta: "New Project",
      },
    ];
  }, [llmCount, projects, teams, navigate]);

  const loaded = llmCount !== null && projects !== null && teams !== null;
  const allDone = loaded && steps.every((s) => s.done);
  const completed = steps.filter((s) => s.done).length;
  const progress = (completed / steps.length) * 100;

  if (!isAdmin || dismissed || !loaded || allDone) return null;

  const handleDismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch {}
    setDismissed(true);
  };

  return (
    <Card
      elevation={0}
      sx={{
        mb: 3,
        p: 2.5,
        borderRadius: 3,
        border: "1px solid",
        borderColor: "primary.main",
        background: `linear-gradient(135deg, ${theme.palette.primary.main}11 0%, ${theme.palette.primary.main}05 100%)`,
        position: "relative",
      }}
    >
      <Tooltip title="Dismiss">
        <IconButton
          size="small"
          onClick={handleDismiss}
          sx={{ position: "absolute", top: 8, right: 8 }}
        >
          <CloseIcon fontSize="small" />
        </IconButton>
      </Tooltip>

      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1 }}>
        <Box
          sx={{
            width: 36, height: 36, borderRadius: 2,
            display: "flex", alignItems: "center", justifyContent: "center",
            bgcolor: "primary.main", color: "#fff",
          }}
        >
          <RocketLaunchIcon fontSize="small" />
        </Box>
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle1" fontWeight={600}>
            Get started with RESTai
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {completed} of {steps.length} steps complete
          </Typography>
        </Box>
      </Stack>

      <LinearProgress
        variant="determinate"
        value={progress}
        sx={{ height: 6, borderRadius: 3, mb: 2 }}
      />

      <Stack spacing={1}>
        {steps.map((step) => {
          const isNext = !step.done && steps.findIndex((s) => !s.done) === steps.indexOf(step);
          const disabled = !step.done && !isNext;
          return (
            <Box
              key={step.key}
              sx={{
                display: "flex", alignItems: "center", gap: 1.5,
                p: 1.5, borderRadius: 2,
                border: "1px solid",
                borderColor: step.done ? "success.light" : isNext ? "primary.light" : "divider",
                bgcolor: step.done ? "success.50" : isNext ? "primary.50" : "transparent",
                opacity: disabled ? 0.6 : 1,
              }}
            >
              {step.done ? (
                <CheckCircleIcon color="success" />
              ) : (
                <RadioButtonUncheckedIcon color={isNext ? "primary" : "disabled"} />
              )}
              <Box sx={{ flex: 1 }}>
                <Typography variant="body2" fontWeight={600} sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                  {step.icon} {step.title}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {step.description}
                </Typography>
              </Box>
              {!step.done && step.action && (
                <Button
                  variant={isNext ? "contained" : "outlined"}
                  size="small"
                  onClick={step.action}
                  disabled={disabled}
                >
                  {step.cta}
                </Button>
              )}
            </Box>
          );
        })}
      </Stack>
    </Card>
  );
}
