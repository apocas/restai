import { useState, useEffect } from "react";
import {
  Box, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Typography, InputAdornment,
} from "@mui/material";
import { AttachMoney, AccountBalance } from "@mui/icons-material";
import { toast } from "react-toastify";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO } from "app/components/page/pageStyles";

/**
 * Platform-admin control to add funds to a team's prepaid wallet (additive
 * top-up — a credit, not an absolute set). The parent gates rendering on
 * `user.is_admin`. `current` is the team's current balance (number | null).
 */
export default function TopUpBalanceDialog({ open, onClose, teamId, current, onSaved }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [value, setValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open) setValue("");
  }, [open]);

  const amount = parseFloat(value);
  const validAmount = Number.isFinite(amount) && amount > 0;
  const currentBalance = current != null && current >= 0 ? Number(current) : 0;
  const newBalance = currentBalance + (validAmount ? amount : 0);

  const submit = () => {
    if (!validAmount) return;
    setSaving(true);
    api.post(`/teams/${teamId}/balance/topup`, { amount }, auth.user.token)
      .then((team) => {
        toast.success(t("teams.balance.added", { amount: "$" + amount.toFixed(2) }), { position: "top-right" });
        onSaved && onSaved(team);
        onClose && onClose();
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontFamily: FONT_MONO, fontSize: "0.95rem", display: "flex", alignItems: "center", gap: 1 }}>
        <AccountBalance fontSize="small" /> {t("teams.balance.dialogTitle")}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {current != null
            ? t("teams.balance.available", { amount: "$" + currentBalance.toFixed(2) })
            : t("teams.balance.walletHelp")}
        </Typography>
        <TextField
          autoFocus fullWidth type="number"
          label={t("teams.balance.addAmount")}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          helperText={t("teams.balance.addHelper")}
          inputProps={{ min: 0, step: 1 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><AttachMoney fontSize="small" /></InputAdornment> }}
        />
        {validAmount && (
          <Box sx={{ mt: 2, p: 1.25, borderRadius: 1, background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.3)" }}>
            <Typography sx={{ fontFamily: FONT_MONO, fontSize: "0.82rem", fontWeight: 700, color: "#059669" }}>
              {t("teams.balance.newBalance", { amount: "$" + newBalance.toFixed(2) })}
            </Typography>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t("common.cancel")}</Button>
        <Button variant="contained" onClick={submit} disabled={saving || !validAmount}>{t("teams.balance.topUp")}</Button>
      </DialogActions>
    </Dialog>
  );
}
