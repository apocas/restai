import { useState, useEffect } from "react";
import {
  Box, Button, Card, Divider, Grid, styled, Typography,
} from "@mui/material";
import { Check, Close, Groups, AccountTree } from "@mui/icons-material";
import Breadcrumb from "app/components/Breadcrumb";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

function InvitationCard({ inv, label, onAccept, onDecline }) {
  const { t } = useTranslation();
  return (
    <Card variant="outlined" sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>{label}</Typography>
      <Typography variant="body2" color="text.secondary">
        {t("invitations.invitedBy", { username: inv.invited_by })}
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        {inv.created_at ? new Date(inv.created_at).toLocaleString() : ""}
      </Typography>
      <Box sx={{ display: "flex", gap: 1 }}>
        <Button variant="contained" color="success" size="small" startIcon={<Check />} onClick={onAccept}>
          {t("invitations.accept")}
        </Button>
        <Button variant="outlined" color="error" size="small" startIcon={<Close />} onClick={onDecline}>
          {t("invitations.decline")}
        </Button>
      </Box>
    </Card>
  );
}

function InvitationSection({ icon: Icon, title, emptyText, invites, nameField, onAccept, onDecline, sx }) {
  return (
    <Card elevation={3} sx={sx}>
      <FlexBox>
        <Icon sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>{title}</H4>
      </FlexBox>
      <Divider />
      {invites.length === 0 ? (
        <Box sx={{ textAlign: "center", py: 4, color: "text.secondary" }}>
          <Typography variant="body2">{emptyText}</Typography>
        </Box>
      ) : (
        <Box sx={{ p: 2 }}>
          <Grid container spacing={2}>
            {invites.map((inv) => (
              <Grid item xs={12} sm={6} md={4} key={`${inv.type}-${inv.id}`}>
                <InvitationCard
                  inv={inv}
                  label={inv[nameField]}
                  onAccept={() => onAccept(inv)}
                  onDecline={() => onDecline(inv)}
                />
              </Grid>
            ))}
          </Grid>
        </Box>
      )}
    </Card>
  );
}

export default function Invitations() {
  const { t } = useTranslation();
  const auth = useAuth();
  const [invitations, setInvitations] = useState([]);

  const fetchInvitations = () => {
    api.get("/invitations", auth.user.token)
      .then(setInvitations)
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("invitations.title");
    fetchInvitations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  // Remove the row from local state immediately so the user gets
  // instant feedback; reconcile on response. On error we refetch to
  // restore the canonical list.
  const actOnInvitation = (inv, action) => {
    const invKey = `${inv.type || "team"}:${inv.id}`;
    const snapshot = invitations;
    setInvitations((prev) => prev.filter((i) => `${i.type || "team"}:${i.id}` !== invKey));

    const base = inv.type === "project"
      ? `/invitations/projects/${inv.id}`
      : `/invitations/${inv.id}`;
    const url = `${base}/${action}`;
    const label = inv.type === "project"
      ? (inv.project_name || `project ${inv.id}`)
      : (inv.team_name || `team ${inv.id}`);
    const verb = action === "accept" ? "joined" : "declined";

    api.post(url, {}, auth.user.token, { silent: true })
      .then(() => {
        const msgKey = action === "accept" ? "invitations.accepted" : "invitations.declined";
        toast.success(t(msgKey, { name: label }), { position: "top-right" });
        window.dispatchEvent(new Event("invitations-changed"));
      })
      .catch(() => {
        // Revert and refetch so stale state doesn't linger.
        setInvitations(snapshot);
        toast.error(t("invitations.failed", {
          action: action === "accept" ? t("invitations.accept").toLowerCase() : t("invitations.decline").toLowerCase(),
          name: label,
        }), { position: "top-right" });
        fetchInvitations();
      });
  };

  const handleAccept = (inv) => actOnInvitation(inv, "accept");
  const handleDecline = (inv) => actOnInvitation(inv, "decline");

  const teamInvites = invitations.filter((inv) => inv.type !== "project");
  const projectInvites = invitations.filter((inv) => inv.type === "project");

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.invitations"), path: "/invitations" }]} />
      </Box>

      <ContentBox>
        <InvitationSection
          icon={Groups}
          title={t("invitations.teamSection")}
          emptyText={t("invitations.noInvitations")}
          invites={teamInvites}
          nameField="team_name"
          onAccept={handleAccept}
          onDecline={handleDecline}
          sx={{ mb: 3 }}
        />
        <InvitationSection
          icon={AccountTree}
          title={t("invitations.projectSection")}
          emptyText={t("invitations.noInvitations")}
          invites={projectInvites}
          nameField="project_name"
          onAccept={handleAccept}
          onDecline={handleDecline}
        />
      </ContentBox>
    </Container>
  );
}
