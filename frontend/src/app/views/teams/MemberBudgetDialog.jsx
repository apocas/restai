import { useState, useEffect } from "react";
import {
  Box, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  LinearProgress, TextField, Typography, InputAdornment,
} from "@mui/material";
import { AttachMoney } from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO } from "app/components/page/pageStyles";

/**
 * Shared editor for a team member's monthly cost cap. Mirrors the API-keys
 * quota dialog: a number field + a spend-vs-cap usage bar + Save/Clear.
 * `member` = { user_id, username, budget (cap|null), spending (MTD) }.
 */
export default function MemberBudgetDialog({ open, onClose, teamId, member, onSaved }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (member) setValue(member.budget != null && member.budget >= 0 ? String(member.budget) : "");
  }, [member]);

  if (!member) return null;

  const spent = Number(member.spending || 0);
  const cap = member.budget != null && member.budget >= 0 ? Number(member.budget) : null;
  const pct = cap ? Math.min(100, Math.round((spent / cap) * 100)) : 0;
  const barColor = pct >= 100 ? "error" : pct >= 80 ? "warning" : "primary";

  const submit = (clear = false) => {
    const n = parseFloat(value);
    const budget = clear ? -1 : (Number.isFinite(n) && n > 0 ? n : -1);
    setSaving(true);
    api.patch(`/teams/${teamId}/members/${member.username}/budget`, { budget }, auth.user.token)
      .then((row) => {
        toast.success(clear || budget < 0 ? t("teams.budget.cleared") : t("teams.budget.saved"), { position: "top-right" });
        onSaved && onSaved(row);
        onClose && onClose();
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontFamily: FONT_MONO, fontSize: "0.95rem" }}>
        {t("teams.budget.dialogTitle")} · {member.username}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t("teams.budget.usedThisMonth", { username: member.username, spent: "$" + spent.toFixed(2) })}
        </Typography>
        {cap != null && (
          <Box sx={{ mb: 2 }}>
            <Typography variant="caption" sx={{ fontFamily: FONT_MONO }}>
              ${spent.toFixed(2)} / ${cap.toFixed(2)} ({pct}%)
            </Typography>
            <LinearProgress variant="determinate" value={pct} color={barColor}
              sx={{ mt: 0.5, height: 6, borderRadius: 1 }} />
          </Box>
        )}
        <TextField
          autoFocus fullWidth type="number"
          label={t("teams.budget.capInput")}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          helperText={t("teams.budget.capHelper")}
          inputProps={{ min: 0, step: 1 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><AttachMoney fontSize="small" /></InputAdornment> }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("common.cancel")}</Button>
        <Button onClick={() => submit(true)} color="warning" disabled={saving}>{t("teams.budget.clear")}</Button>
        <Button variant="contained" onClick={() => submit(false)} disabled={saving}>{t("common.save")}</Button>
      </DialogActions>
    </Dialog>
  );
}
