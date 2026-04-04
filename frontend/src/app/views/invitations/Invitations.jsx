import { useState, useEffect } from "react";
import {
  Box, Button, Card, Divider, Grid, styled, Typography,
} from "@mui/material";
import { Check, Close, Groups, AccountTree } from "@mui/icons-material";
import Breadcrumb from "app/components/Breadcrumb";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

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
  return (
    <Card variant="outlined" sx={{ p: 2 }}>
      <Typography variant="h6" gutterBottom>{label}</Typography>
      <Typography variant="body2" color="text.secondary">
        Invited by <strong>{inv.invited_by}</strong>
      </Typography>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
        {inv.created_at ? new Date(inv.created_at).toLocaleString() : ""}
      </Typography>
      <Box sx={{ display: "flex", gap: 1 }}>
        <Button variant="contained" color="success" size="small" startIcon={<Check />} onClick={onAccept}>
          Accept
        </Button>
        <Button variant="outlined" color="error" size="small" startIcon={<Close />} onClick={onDecline}>
          Decline
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
  const auth = useAuth();
  const [invitations, setInvitations] = useState([]);

  const fetchInvitations = () => {
    api.get("/invitations", auth.user.token)
      .then(setInvitations)
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Invitations";
    fetchInvitations();
  }, []);

  const handleAccept = (inv) => {
    const url = inv.type === "project"
      ? `/invitations/projects/${inv.id}/accept`
      : `/invitations/${inv.id}/accept`;
    api.post(url, {}, auth.user.token)
      .then(() => { fetchInvitations(); window.dispatchEvent(new Event("invitations-changed")); })
      .catch(() => {});
  };

  const handleDecline = (inv) => {
    const url = inv.type === "project"
      ? `/invitations/projects/${inv.id}/decline`
      : `/invitations/${inv.id}/decline`;
    api.post(url, {}, auth.user.token)
      .then(() => { fetchInvitations(); window.dispatchEvent(new Event("invitations-changed")); })
      .catch(() => {});
  };

  const teamInvites = invitations.filter((inv) => inv.type !== "project");
  const projectInvites = invitations.filter((inv) => inv.type === "project");

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Invitations", path: "/invitations" }]} />
      </Box>

      <ContentBox>
        <InvitationSection
          icon={Groups}
          title="Team Invitations"
          emptyText="No pending team invitations"
          invites={teamInvites}
          nameField="team_name"
          onAccept={handleAccept}
          onDecline={handleDecline}
          sx={{ mb: 3 }}
        />
        <InvitationSection
          icon={AccountTree}
          title="Project Invitations"
          emptyText="No pending project invitations"
          invites={projectInvites}
          nameField="project_name"
          onAccept={handleAccept}
          onDecline={handleDecline}
        />
      </ContentBox>
    </Container>
  );
}
