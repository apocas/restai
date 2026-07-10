import { useState } from "react";
import { Box, Button, Card, Chip, Grid, TextField, Typography, styled } from "@mui/material";
import { Shield, PersonAdd } from "@mui/icons-material";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import ContentCard from "app/components/page/ContentCard";
import { PALETTE, ACCENT, FONT_DISPLAY } from "./forensic/styles";

const SectionTitle = styled(Typography)(({ theme }) => ({
  fontFamily: FONT_DISPLAY,
  fontWeight: 600,
  fontSize: "0.7rem",
  letterSpacing: "0.18em",
  textTransform: "uppercase",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.75),
  color: ACCENT,
  marginBottom: theme.spacing(1.5),
}));

const DetailItem = ({ label, children }) => (
  <Grid item xs={12} sm={6} md={4}>
    <Typography variant="caption" color="text.secondary" display="block">
      {label}
    </Typography>
    {children}
  </Grid>
);

export default function ProjectInfoSecurity({ project }) {
  const auth = useAuth();
  const [inviteUsername, setInviteUsername] = useState("");

  const handleInvite = () => {
    if (!inviteUsername.trim()) return;
    api.post(`/projects/${project.id}/invitations`, { username: inviteUsername.trim() }, auth.user.token)
      .then((d) => {
        toast.success(d.message || "Invitation sent");
        setInviteUsername("");
      })
      .catch(() => {});
  };

  return (
    <ContentCard
      icon={<Shield />}
      title="Security"
      subtitle={`PROJECT/${String(project.id).padStart(4, "0")} · GUARDS · ACCESS`}
    >
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card elevation={0} sx={{ p: 2.5, background: "rgba(255,255,255,0.55)", border: `1px solid ${PALETTE.edge}` }}>
          <SectionTitle><Shield fontSize="small" /> Guards</SectionTitle>
          <Grid container spacing={2}>
            <DetailItem label="Input Guard">
              {project.guard ? (
                <Chip label={project.guard_name || project.guard} size="small" color="warning" variant="outlined" />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Disabled
                </Typography>
              )}
            </DetailItem>
            <DetailItem label="Output Guard">
              {project.options?.guard_output ? (
                <Chip
                  label={project.guard_output_name || project.options.guard_output}
                  size="small"
                  color="warning"
                  variant="outlined"
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Disabled
                </Typography>
              )}
            </DetailItem>
            {project.options?.guard_mode && (project.guard || project.options?.guard_output) && (
              <DetailItem label="Guard Mode">
                <Chip
                  label={project.options.guard_mode === "warn" ? "Warn" : "Block"}
                  size="small"
                  color={project.options.guard_mode === "warn" ? "warning" : "error"}
                  variant="outlined"
                />
              </DetailItem>
            )}
            {project.censorship && (
              <Grid item xs={12} sm={8}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Censorship Message
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                    fontStyle: "italic",
                    bgcolor: "action.hover",
                    p: 1,
                    borderRadius: 1,
                    mt: 0.5,
                  }}
                >
                  {project.censorship}
                </Typography>
              </Grid>
            )}
          </Grid>
        </Card>
      </Grid>

      {/* Invite User */}
      <Grid item xs={12}>
        <Card elevation={0} sx={{ p: 2.5, background: "rgba(255,255,255,0.55)", border: `1px solid ${PALETTE.edge}` }}>
          <SectionTitle><PersonAdd fontSize="small" /> Invite User</SectionTitle>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 2 }}>
            Invite a team member to this project by username. They will be able to accept or decline.
          </Typography>
          <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
            <TextField
              size="small"
              label="Username"
              value={inviteUsername}
              onChange={(e) => setInviteUsername(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handleInvite(); }}
              sx={{ minWidth: 250 }}
            />
            <Button
              variant="contained"
              size="medium"
              disabled={!inviteUsername.trim()}
              onClick={handleInvite}
              startIcon={<PersonAdd />}
            >
              Send Invite
            </Button>
          </Box>
        </Card>
      </Grid>
    </Grid>
    </ContentCard>
  );
}
