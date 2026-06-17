import { useState, useEffect } from "react";
import { Link as RouterLink } from "react-router-dom";
import {
  Box, Card, Grid, Chip, Link, LinearProgress, Typography,
} from "@mui/material";
import { Group } from "@mui/icons-material";

import { H5, Paragraph } from "app/components/Typography";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { forensicCardSx, loadFonts } from "app/views/projects/components/forensic/styles";
import { FONT_MONO } from "app/components/page/pageStyles";

const ACCENT = "#4338ca";

const teamCardSx = {
  height: "100%",
  borderRadius: 2,
  border: "1px solid rgba(15,23,42,0.08)",
  transition: "border-color .2s ease, box-shadow .2s ease, transform .2s ease",
  "&:hover": {
    borderColor: "rgba(67,56,202,0.35)",
    boxShadow: "0 6px 18px rgba(67,56,202,0.10)",
    transform: "translateY(-1px)",
  },
};

const adminChipSx = {
  fontFamily: FONT_MONO, fontSize: "0.62rem", fontWeight: 700, height: 20,
  color: ACCENT, background: "rgba(67,56,202,0.10)", border: "1px solid rgba(67,56,202,0.30)",
};
const memberChipSx = {
  fontFamily: FONT_MONO, fontSize: "0.62rem", fontWeight: 700, height: 20,
  color: "text.secondary", background: "rgba(15,23,42,0.04)", border: "1px solid rgba(15,23,42,0.10)",
};

function BudgetBar({ spending, budget, t }) {
  const spent = Number(spending || 0);
  const cap = budget != null && budget >= 0 ? Number(budget) : null;

  if (cap == null) {
    return (
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem", color: "text.secondary" }}>
        {t("users.userTeams.spentThisMonth", { spent: "$" + spent.toFixed(2) })}
        <Box component="span" sx={{ color: "text.disabled", ml: 0.75 }}>· {t("users.userTeams.uncapped")}</Box>
      </Typography>
    );
  }

  const pct = cap > 0 ? Math.min(100, Math.round((spent / cap) * 100)) : 100;
  const color = pct >= 100 ? "error" : pct >= 80 ? "warning" : "primary";
  const remaining = Math.max(0, cap - spent);
  return (
    <Box>
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", mb: 0.5 }}>
        <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.72rem", fontWeight: 700 }}>
          ${spent.toFixed(2)} <Box component="span" sx={{ color: "text.disabled", fontWeight: 400 }}>/ ${cap.toFixed(2)}</Box>
        </Typography>
        <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.68rem", color: pct >= 100 ? "#ef4444" : pct >= 80 ? "#f59e0b" : "text.secondary" }}>
          {pct}%
        </Typography>
      </Box>
      <LinearProgress variant="determinate" value={pct} color={color} sx={{ height: 6, borderRadius: 1 }} />
      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.64rem", color: "text.disabled", mt: 0.5, display: "block" }}>
        {t("users.userTeams.remaining", { amount: "$" + remaining.toFixed(2) })}
      </Typography>
    </Box>
  );
}

export default function Teams({ user }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [budgets, setBudgets] = useState(null);

  useEffect(() => { loadFonts(); }, []);

  useEffect(() => {
    if (!user.username) return;
    api.get(`/users/${user.username}/team-budgets`, auth.user.token, { silent: true })
      .then((d) => setBudgets(d.teams || []))
      .catch(() => setBudgets(null));
  }, [user.username]);

  // Team descriptions aren't on the budget payload — pull them from the user profile.
  const descById = {};
  [...(user.teams || []), ...(user.admin_teams || [])].forEach((tm) => { descById[tm.id] = tm.description; });

  // Prefer the budget endpoint; fall back to the profile's team lists (name + role only)
  // so the tab still renders if the call fails or the backend is older.
  const fallback = () => {
    const adminIds = new Set((user.admin_teams || []).map((tm) => tm.id));
    const map = new Map();
    (user.admin_teams || []).forEach((tm) =>
      map.set(tm.id, { team_id: tm.id, team_name: tm.name, is_admin: true, budget: null, spending: 0 }));
    (user.teams || []).forEach((tm) => {
      if (!map.has(tm.id)) map.set(tm.id, { team_id: tm.id, team_name: tm.name, is_admin: adminIds.has(tm.id), budget: null, spending: 0 });
    });
    return [...map.values()].sort((a, b) => (a.team_name || "").localeCompare(b.team_name || ""));
  };

  const teams = budgets != null ? budgets : fallback();
  const isEmpty = teams.length === 0;

  return (
    <Card elevation={0} sx={{ ...forensicCardSx, padding: 3 }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
        <Group sx={{ fontSize: 18, color: ACCENT }} />
        <H5 sx={{ m: 0 }}>{t("users.userTeams.title")}</H5>
        {!isEmpty && (
          <Box sx={{ fontFamily: FONT_MONO, fontSize: "0.66rem", fontWeight: 700, color: "text.secondary",
            px: 0.9, py: 0.2, borderRadius: 0.75, background: "rgba(15,23,42,0.04)", border: "1px solid rgba(15,23,42,0.08)" }}>
            {teams.length}
          </Box>
        )}
      </Box>

      {isEmpty ? (
        <Paragraph color="textSecondary">{t("users.userTeams.noTeams")}</Paragraph>
      ) : (
        <Grid container spacing={2}>
          {teams.map((team) => (
            <Grid item xs={12} sm={6} md={4} key={team.team_id}>
              <Card variant="outlined" sx={teamCardSx}>
                <Box sx={{ p: 2 }}>
                  <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 1 }}>
                    <Link
                      component={RouterLink}
                      to={`/team/${team.team_id}`}
                      sx={{ fontWeight: 700, fontSize: "0.95rem", color: "#0f172a", textDecoration: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        "&:hover": { color: ACCENT, textDecoration: "underline" } }}
                    >
                      {team.team_name}
                    </Link>
                    <Chip
                      size="small"
                      label={team.is_admin ? t("users.userTeams.admin") : t("users.userTeams.member")}
                      sx={team.is_admin ? adminChipSx : memberChipSx}
                    />
                  </Box>

                  {descById[team.team_id] && (
                    <Typography variant="caption" color="text.secondary"
                      sx={{ display: "block", mt: 0.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {descById[team.team_id]}
                    </Typography>
                  )}

                  <Box sx={{ mt: 1.75, pt: 1.5, borderTop: "1px solid rgba(15,23,42,0.06)" }}>
                    <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.58rem", letterSpacing: "0.12em", textTransform: "uppercase", color: "text.secondary", mb: 0.75 }}>
                      {t("users.userTeams.yourBudget")}
                    </Typography>
                    <BudgetBar spending={team.spending} budget={team.budget} t={t} />
                    {team.team_balance != null && (
                      <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.64rem", mt: 0.75, display: "block",
                        color: team.team_balance <= 0 ? "#ef4444" : "text.disabled" }}>
                        {team.team_balance <= 0
                          ? t("teams.balance.depleted")
                          : t("users.userTeams.teamWallet", { amount: "$" + Number(team.team_balance).toFixed(2) })}
                      </Typography>
                    )}
                  </Box>
                </Box>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Card>
  );
}
