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
import { useTranslation } from "react-i18next";

export default function Teams({ user }) {
  const { t } = useTranslation();
  const memberTeams = user.teams || [];
  const adminTeams = user.admin_teams || [];

  const adminIds = new Set(adminTeams.map((tm) => tm.id));
  const memberOnly = memberTeams.filter((tm) => !adminIds.has(tm.id));

  const isEmpty = adminTeams.length === 0 && memberOnly.length === 0;

  const renderRow = (team, role) => (
    <Fragment key={`${role}-${team.id}`}>
      <ListItem
        secondaryAction={
          <Chip
            label={role === "admin" ? t("users.userTeams.admin") : t("users.userTeams.member")}
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
      <H5 sx={{ mb: 2 }}>{t("users.userTeams.title")}</H5>

      {isEmpty ? (
        <Paragraph color="textSecondary">
          {t("users.userTeams.noTeams")}
        </Paragraph>
      ) : (
        <Grid container spacing={3}>
          <Grid item xs={12} md={6}>
            <Box sx={{ mb: 1 }}>
              <H5 sx={{ fontSize: "1rem" }}>{t("users.userTeams.adminOf")}</H5>
            </Box>
            {adminTeams.length > 0 ? (
              <List>{adminTeams.map((tm) => renderRow(tm, "admin"))}</List>
            ) : (
              <Paragraph color="textSecondary">{t("users.userTeams.noAdmin")}</Paragraph>
            )}
          </Grid>

          <Grid item xs={12} md={6}>
            <Box sx={{ mb: 1 }}>
              <H5 sx={{ fontSize: "1rem" }}>{t("users.userTeams.memberOf")}</H5>
            </Box>
            {memberOnly.length > 0 ? (
              <List>{memberOnly.map((tm) => renderRow(tm, "member"))}</List>
            ) : (
              <Paragraph color="textSecondary">{t("users.userTeams.noMember")}</Paragraph>
            )}
          </Grid>
        </Grid>
      )}
    </Card>
  );
}
