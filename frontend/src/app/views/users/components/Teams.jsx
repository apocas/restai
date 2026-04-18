import { Fragment } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Box,
  Card,
  Grid,
  Chip,
  List,
  ListItem,
  ListItemText,
  Divider,
  Link,
} from "@mui/material";

import { H5, Paragraph } from "app/components/Typography";

export default function Teams({ user }) {
  const memberTeams = user.teams || [];
  const adminTeams = user.admin_teams || [];

  const adminIds = new Set(adminTeams.map((t) => t.id));
  const memberOnly = memberTeams.filter((t) => !adminIds.has(t.id));

  const isEmpty = adminTeams.length === 0 && memberOnly.length === 0;

  const renderRow = (team, role) => (
    <Fragment key={`${role}-${team.id}`}>
      <ListItem
        secondaryAction={
          <Chip
            label={role === "admin" ? "Admin" : "Member"}
            color={role === "admin" ? "primary" : "default"}
            size="small"
          />
        }
      >
        <ListItemText
          primary={
            <Link component={RouterLink} to={`/team/${team.id}`} underline="hover">
              {team.name}
            </Link>
          }
          secondary={team.description || null}
        />
      </ListItem>
      <Divider component="li" />
    </Fragment>
  );

  return (
    <Card sx={{ padding: 3 }}>
      <H5 sx={{ mb: 2 }}>Teams</H5>

      {isEmpty ? (
        <Paragraph color="textSecondary">
          This user is not a member of any team.
        </Paragraph>
      ) : (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Box sx={{ mb: 1 }}>
              <H5 sx={{ fontSize: "1rem" }}>Admin of</H5>
            </Box>
            {adminTeams.length > 0 ? (
              <List>{adminTeams.map((t) => renderRow(t, "admin"))}</List>
            ) : (
              <Paragraph color="textSecondary">Not an admin of any team.</Paragraph>
            )}
          </Grid>

          <Grid item xs={12} md={6}>
            <Box sx={{ mb: 1 }}>
              <H5 sx={{ fontSize: "1rem" }}>Member of</H5>
            </Box>
            {memberOnly.length > 0 ? (
              <List>{memberOnly.map((t) => renderRow(t, "member"))}</List>
            ) : (
              <Paragraph color="textSecondary">No additional team memberships.</Paragraph>
            )}
          </Grid>
        </Grid>
      )}
    </Card>
  );
}
