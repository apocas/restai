import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, Button, Card, Chip, IconButton, LinearProgress, Stack, Tooltip,
  Typography, useTheme, alpha,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";
import CloseIcon from "@mui/icons-material/Close";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
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

  // QA override: ?onboarding=force renders the card even when dismissed
  // and even when all 3 steps are already complete.
  const force = (() => {
    try { return new URLSearchParams(window.location.search).get("onboarding") === "force"; } catch { return false; }
  })();

  const isAdmin = auth?.user?.is_admin;

  useEffect(() => {
    if (!isAdmin || (dismissed && !force)) return;

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
        description: "Configure your first LLM so projects can call models.",
        icon: PsychologyIcon,
        done: llmCount !== null && llmCount > 0,
        action: () => navigate("/llms/new"),
        cta: "Add LLM",
      },
      {
        key: "team_llm",
        title: "Add the LLM to a team",
        description: "Attach the LLM to a team so projects in that team can use it. The Default Team is created on install.",
        icon: GroupsIcon,
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
        icon: AssignmentIcon,
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
  const nextIdx = steps.findIndex((s) => !s.done);

  if (!isAdmin) return null;
  if (!loaded) return null;
  if (!force && (dismissed || allDone)) return null;

  const handleDismiss = () => {
    try { localStorage.setItem(DISMISS_KEY, "1"); } catch {}
    setDismissed(true);
  };

  const primary = theme.palette.primary.main;
  const secondary = theme.palette.secondary?.main || theme.palette.primary.dark;

  return (
    <Card
      elevation={0}
      sx={{
        mb: 4,
        borderRadius: 4,
        border: "1px solid",
        borderColor: alpha(primary, 0.18),
        overflow: "hidden",
        position: "relative",
        background: theme.palette.mode === "dark"
          ? `linear-gradient(135deg, ${alpha(primary, 0.08)} 0%, ${theme.palette.background.paper} 70%)`
          : `linear-gradient(135deg, ${alpha(primary, 0.05)} 0%, #ffffff 70%)`,
      }}
    >
      {/* Decorative blur orbs */}
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          top: -120, right: -120,
          width: 320, height: 320,
          borderRadius: "50%",
          background: `linear-gradient(135deg, ${primary}, ${secondary})`,
          filter: "blur(80px)",
          opacity: 0.12,
          pointerEvents: "none",
        }}
      />
      <Box
        aria-hidden
        sx={{
          position: "absolute",
          bottom: -100, left: -80,
          width: 240, height: 240,
          borderRadius: "50%",
          background: `linear-gradient(135deg, ${secondary}, ${primary})`,
          filter: "blur(70px)",
          opacity: 0.08,
          pointerEvents: "none",
        }}
      />

      {/* Header */}
      <Box sx={{ p: 3, pb: 2.5, display: "flex", alignItems: "center", gap: 2, position: "relative" }}>
        <Box
          sx={{
            width: 52, height: 52, borderRadius: 3,
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "#fff",
            background: `linear-gradient(135deg, ${primary}, ${secondary})`,
            boxShadow: `0 8px 20px ${alpha(primary, 0.35)}`,
            flexShrink: 0,
          }}
        >
          <RocketLaunchIcon />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h6" fontWeight={700} sx={{ lineHeight: 1.2 }}>
            Welcome to RESTai
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
            A few quick steps and you'll be live with your first AI project.
          </Typography>
        </Box>
        <Chip
          size="small"
          label={`${completed} / ${steps.length}`}
          sx={{
            fontWeight: 700,
            bgcolor: alpha(primary, 0.12),
            color: primary,
            border: `1px solid ${alpha(primary, 0.25)}`,
          }}
        />
        <Tooltip title="Dismiss">
          <IconButton size="small" onClick={handleDismiss} aria-label="dismiss onboarding">
            <CloseIcon fontSize="small" />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Progress bar */}
      <Box sx={{ px: 3, position: "relative" }}>
        <LinearProgress
          variant="determinate"
          value={progress}
          sx={{
            height: 6,
            borderRadius: 99,
            bgcolor: alpha(primary, 0.1),
            "& .MuiLinearProgress-bar": {
              borderRadius: 99,
              background: `linear-gradient(90deg, ${primary}, ${secondary})`,
            },
          }}
        />
      </Box>

      {/* Steps */}
      <Stack spacing={1.5} sx={{ p: 3, position: "relative" }}>
        {steps.map((step, idx) => {
          const isNext = idx === nextIdx;
          const StepIcon = step.icon;

          // Visual states for the numbered/check circle
          let bubbleBg, bubbleColor, bubbleBorder, bubbleShadow;
          if (step.done) {
            bubbleBg = `linear-gradient(135deg, ${theme.palette.success.main}, ${theme.palette.success.dark})`;
            bubbleColor = "#fff";
            bubbleBorder = "transparent";
            bubbleShadow = `0 4px 12px ${alpha(theme.palette.success.main, 0.35)}`;
          } else if (isNext) {
            bubbleBg = `linear-gradient(135deg, ${primary}, ${secondary})`;
            bubbleColor = "#fff";
            bubbleBorder = "transparent";
            bubbleShadow = `0 4px 12px ${alpha(primary, 0.35)}`;
          } else {
            bubbleBg = "transparent";
            bubbleColor = theme.palette.text.disabled;
            bubbleBorder = alpha(theme.palette.text.disabled, 0.4);
            bubbleShadow = "none";
          }

          // Card-row visual state
          const rowBg = step.done
            ? alpha(theme.palette.success.main, theme.palette.mode === "dark" ? 0.08 : 0.05)
            : isNext
              ? alpha(primary, theme.palette.mode === "dark" ? 0.1 : 0.06)
              : "transparent";
          const rowBorder = step.done
            ? alpha(theme.palette.success.main, 0.25)
            : isNext
              ? alpha(primary, 0.3)
              : theme.palette.divider;

          return (
            <Box
              key={step.key}
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 2,
                p: 2,
                borderRadius: 3,
                border: "1px solid",
                borderColor: rowBorder,
                bgcolor: rowBg,
                transition: "all 0.2s ease",
                ...(isNext && !step.done && {
                  boxShadow: `0 4px 16px ${alpha(primary, 0.12)}`,
                  "&:hover": { transform: "translateY(-1px)", boxShadow: `0 6px 20px ${alpha(primary, 0.18)}` },
                }),
              }}
            >
              {/* Number / check bubble */}
              <Box
                sx={{
                  width: 40, height: 40, borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  background: bubbleBg,
                  color: bubbleColor,
                  border: `1.5px solid ${bubbleBorder}`,
                  boxShadow: bubbleShadow,
                  flexShrink: 0,
                  fontWeight: 700,
                  fontSize: 14,
                }}
              >
                {step.done ? <CheckCircleIcon fontSize="small" /> : idx + 1}
              </Box>

              {/* Step icon */}
              <Box
                sx={{
                  width: 36, height: 36, borderRadius: 2,
                  display: { xs: "none", sm: "flex" }, alignItems: "center", justifyContent: "center",
                  bgcolor: step.done
                    ? alpha(theme.palette.success.main, 0.12)
                    : isNext
                      ? alpha(primary, 0.12)
                      : alpha(theme.palette.text.disabled, 0.08),
                  color: step.done
                    ? theme.palette.success.main
                    : isNext
                      ? primary
                      : theme.palette.text.disabled,
                  flexShrink: 0,
                }}
              >
                <StepIcon fontSize="small" />
              </Box>

              {/* Text */}
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography
                  variant="body1"
                  fontWeight={600}
                  sx={{
                    color: step.done ? "text.primary" : isNext ? "text.primary" : "text.secondary",
                    textDecoration: step.done ? "none" : "none",
                  }}
                >
                  {step.title}
                </Typography>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mt: 0.25, display: { xs: "none", sm: "block" } }}
                >
                  {step.description}
                </Typography>
              </Box>

              {/* CTA */}
              {!step.done && step.action && (
                <Button
                  variant={isNext ? "contained" : "outlined"}
                  size="small"
                  onClick={step.action}
                  endIcon={isNext ? <ArrowForwardIcon /> : null}
                  sx={{
                    flexShrink: 0,
                    borderRadius: 2,
                    textTransform: "none",
                    fontWeight: 600,
                    px: 2,
                    ...(isNext && {
                      background: `linear-gradient(135deg, ${primary}, ${secondary})`,
                      boxShadow: `0 4px 12px ${alpha(primary, 0.3)}`,
                      "&:hover": {
                        background: `linear-gradient(135deg, ${primary}, ${secondary})`,
                        opacity: 0.92,
                        boxShadow: `0 6px 16px ${alpha(primary, 0.4)}`,
                      },
                    }),
                  }}
                >
                  {step.cta}
                </Button>
              )}
              {step.done && (
                <Chip
                  size="small"
                  label="Done"
                  sx={{
                    flexShrink: 0,
                    fontWeight: 600,
                    bgcolor: alpha(theme.palette.success.main, 0.12),
                    color: theme.palette.success.main,
                    border: `1px solid ${alpha(theme.palette.success.main, 0.25)}`,
                  }}
                />
              )}
            </Box>
          );
        })}
      </Stack>
    </Card>
  );
}
