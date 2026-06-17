import { useState, useEffect } from "react";
import {
  Button, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, Typography, InputAdornment, FormControlLabel, Checkbox,
  RadioGroup, Radio, FormControl, FormLabel,
} from "@mui/material";
import { AttachMoney, CreditCard } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO } from "app/components/page/pageStyles";

const PROVIDER_LABELS = { stripe: "Stripe", paypal: "PayPal" };

/**
 * Team-admin self-service top-up via a hosted payment provider. Creates a
 * checkout session and redirects the browser to the provider's hosted page;
 * the wallet is credited by the provider webhook on return.
 */
export default function PaymentCheckoutDialog({ open, onClose, teamId, providers = [], autoRechargeProviders = [] }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [value, setValue] = useState("");
  const [provider, setProvider] = useState(providers[0] || "stripe");
  const [saveCard, setSaveCard] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setValue("");
      setSaveCard(false);
      setProvider(providers[0] || "stripe");
    }
  }, [open, providers]);

  const amount = parseFloat(value);
  const validAmount = Number.isFinite(amount) && amount > 0;
  const canSaveCard = autoRechargeProviders.includes(provider);

  const submit = () => {
    if (!validAmount) return;
    setBusy(true);
    api.post(`/teams/${teamId}/balance/checkout`, { amount, provider, save_method: canSaveCard && saveCard }, auth.user.token)
      .then((res) => {
        if (res && res.redirect_url) {
          window.location.href = res.redirect_url;  // hand off to the hosted checkout
        } else {
          setBusy(false);
        }
      })
      .catch(() => setBusy(false));
  };

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontFamily: FONT_MONO, fontSize: "0.95rem", display: "flex", alignItems: "center", gap: 1 }}>
        <CreditCard fontSize="small" /> {t("teams.payment.addFunds")}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          {t("teams.payment.checkoutHelp")}
        </Typography>
        <TextField
          autoFocus fullWidth type="number"
          label={t("teams.payment.amount")}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          inputProps={{ min: 0, step: 1 }}
          InputProps={{ startAdornment: <InputAdornment position="start"><AttachMoney fontSize="small" /></InputAdornment> }}
        />
        {providers.length > 1 && (
          <FormControl sx={{ mt: 2 }}>
            <FormLabel sx={{ fontSize: "0.8rem" }}>{t("teams.payment.provider")}</FormLabel>
            <RadioGroup row value={provider} onChange={(e) => setProvider(e.target.value)}>
              {providers.map((p) => (
                <FormControlLabel key={p} value={p} control={<Radio size="small" />} label={PROVIDER_LABELS[p] || p} />
              ))}
            </RadioGroup>
          </FormControl>
        )}
        {canSaveCard && (
          <FormControlLabel
            sx={{ mt: 1, display: "block" }}
            control={<Checkbox size="small" checked={saveCard} onChange={(e) => setSaveCard(e.target.checked)} />}
            label={<Typography variant="body2">{t("teams.payment.saveCard")}</Typography>}
          />
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>{t("common.cancel")}</Button>
        <Button variant="contained" onClick={submit} disabled={busy || !validAmount}>
          {t("teams.payment.continue")}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
