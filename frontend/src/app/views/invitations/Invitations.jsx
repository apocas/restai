import { useState, useEffect } from "react";
import {
  Box, Button, Card, Divider, Grid, styled, Typography,
} from "@mui/material";
import { Check, Close, Groups } from "@mui/icons-material";
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

  const handleAccept = (id) => {
    api.post(`/invitations/${id}/accept`, {}, auth.user.token)
      .then(() => fetchInvitations())
      .catch(() => {});
  };

  const handleDecline = (id) => {
    api.post(`/invitations/${id}/decline`, {}, auth.user.token)
      .then(() => fetchInvitations())
      .catch(() => {});
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Invitations", path: "/invitations" }]} />
      </Box>

      <ContentBox>
        <Card elevation={3}>
          <FlexBox>
            <Groups sx={{ ml: 2 }} />
            <H4 sx={{ p: 2 }}>Team Invitations</H4>
          </FlexBox>
          <Divider />

          {invitations.length === 0 ? (
            <Box sx={{ textAlign: "center", py: 6, color: "text.secondary" }}>
              <Groups sx={{ fontSize: 48, opacity: 0.3, mb: 1 }} />
              <Typography variant="body1">No pending invitations</Typography>
            </Box>
          ) : (
            <Box sx={{ p: 2 }}>
              <Grid container spacing={2}>
                {invitations.map((inv) => (
                  <Grid item xs={12} sm={6} md={4} key={inv.id}>
                    <Card variant="outlined" sx={{ p: 2 }}>
                      <Typography variant="h6" gutterBottom>{inv.team_name}</Typography>
                      <Typography variant="body2" color="text.secondary">
                        Invited by <strong>{inv.invited_by}</strong>
                      </Typography>
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                        {inv.created_at ? new Date(inv.created_at).toLocaleString() : ""}
                      </Typography>
                      <Box sx={{ display: "flex", gap: 1 }}>
                        <Button
                          variant="contained"
                          color="success"
                          size="small"
                          startIcon={<Check />}
                          onClick={() => handleAccept(inv.id)}
                        >
                          Accept
                        </Button>
                        <Button
                          variant="outlined"
                          color="error"
                          size="small"
                          startIcon={<Close />}
                          onClick={() => handleDecline(inv.id)}
                        >
                          Decline
                        </Button>
                      </Box>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Box>
          )}
        </Card>
      </ContentBox>
    </Container>
  );
}
