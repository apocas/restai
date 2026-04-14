import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, Divider, Grid, TextField, Typography, Alert, styled,
} from "@mui/material";
import { LoadingButton } from "@mui/lab";
import { QRCodeSVG } from "qrcode.react";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { toast } from "react-toastify";

const RecoveryBox = styled(Box)(({ theme }) => ({
  display: "grid",
  gridTemplateColumns: "repeat(4, 1fr)",
  gap: theme.spacing(1),
  padding: theme.spacing(2),
  backgroundColor: theme.palette.grey[100],
  borderRadius: theme.shape.borderRadius,
  fontFamily: "monospace",
  fontSize: "0.9rem",
}));

export default function TwoFactorAuth({ user }) {
  const auth = useAuth();
  const [status, setStatus] = useState({ enabled: false, enforced: false });
  const [setup, setSetup] = useState(null); // { secret, provisioning_uri, recovery_codes }
  const [confirmCode, setConfirmCode] = useState("");
  const [enablePassword, setEnablePassword] = useState("");
  const [disablePassword, setDisablePassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [showDisable, setShowDisable] = useState(false);

  const isSelf = auth.user?.username === user?.username;

  const fetchStatus = () => {
    if (!user?.username) return;
    api.get(`/users/${user.username}/totp/status`, auth.user.token)
      .then(setStatus)
      .catch(() => {});
  };

  useEffect(() => { fetchStatus(); }, [user?.username]);

  const handleSetup = async () => {
    setLoading(true);
    try {
      const data = await api.post(`/users/${user.username}/totp/setup`, {}, auth.user.token);
      setSetup(data);
    } catch (e) {
      toast.error("Failed to setup 2FA");
    } finally {
      setLoading(false);
    }
  };

  const handleEnable = async () => {
    setLoading(true);
    try {
      await api.post(`/users/${user.username}/totp/enable`, { code: confirmCode, password: enablePassword }, auth.user.token);
      toast.success("2FA enabled successfully");
      setSetup(null);
      setConfirmCode("");
      setEnablePassword("");
      fetchStatus();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Invalid code");
    } finally {
      setLoading(false);
    }
  };

  const handleDisable = async () => {
    setLoading(true);
    try {
      await api.post(`/users/${user.username}/totp/disable`, { password: disablePassword }, auth.user.token);
      toast.success("2FA disabled");
      setDisablePassword("");
      setShowDisable(false);
      fetchStatus();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Failed to disable 2FA");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card sx={{ p: 3 }}>
      <Typography variant="h6" gutterBottom>Two-Factor Authentication</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Add an extra layer of security using a TOTP authenticator app (Google Authenticator, Authy, etc.).
      </Typography>

      {status.enforced && (
        <Alert severity="info" sx={{ mb: 2 }}>
          2FA is enforced by the administrator for all local users.
        </Alert>
      )}

      <Box sx={{ mb: 2 }}>
        <Chip
          label={status.enabled ? "2FA Enabled" : "2FA Disabled"}
          color={status.enabled ? "success" : "default"}
          variant="outlined"
        />
      </Box>

      <Divider sx={{ my: 2 }} />

      {/* Setup flow — not yet enabled */}
      {!status.enabled && !setup && (
        <LoadingButton variant="contained" loading={loading} onClick={handleSetup}>
          Set Up 2FA
        </LoadingButton>
      )}

      {/* QR code + recovery codes + confirmation */}
      {setup && !status.enabled && (
        <Box>
          <Typography variant="subtitle1" gutterBottom>1. Scan this QR code with your authenticator app</Typography>
          <Box sx={{ display: "flex", gap: 3, mb: 3, flexWrap: "wrap" }}>
            <Box sx={{ p: 2, bgcolor: "#fff", borderRadius: 1, display: "inline-block" }}>
              <QRCodeSVG value={setup.provisioning_uri} size={180} />
            </Box>
            <Box>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Or enter this key manually:
              </Typography>
              <Typography variant="body2" fontFamily="monospace" sx={{
                bgcolor: "grey.100", p: 1, borderRadius: 1, wordBreak: "break-all", maxWidth: 280,
              }}>
                {setup.secret}
              </Typography>
            </Box>
          </Box>

          <Typography variant="subtitle1" gutterBottom>2. Save your recovery codes</Typography>
          <Alert severity="warning" sx={{ mb: 1 }}>
            Store these codes securely. Each code can only be used once to log in if you lose your authenticator.
          </Alert>
          <RecoveryBox>
            {setup.recovery_codes.map((code, i) => (
              <Typography key={i} variant="body2" fontFamily="monospace">{code}</Typography>
            ))}
          </RecoveryBox>

          <Typography variant="subtitle1" sx={{ mt: 3, mb: 1 }}>3. Confirm with a code and your password</Typography>
          <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
            <TextField
              size="small"
              label="6-digit code"
              value={confirmCode}
              onChange={(e) => setConfirmCode(e.target.value)}
              inputProps={{ maxLength: 6, autoComplete: "one-time-code" }}
              sx={{ width: 160 }}
            />
            <TextField
              size="small"
              type="password"
              label="Password"
              value={enablePassword}
              onChange={(e) => setEnablePassword(e.target.value)}
              sx={{ width: 200 }}
            />
            <LoadingButton variant="contained" loading={loading} onClick={handleEnable} disabled={confirmCode.length < 6 || !enablePassword}>
              Enable 2FA
            </LoadingButton>
          </Box>
        </Box>
      )}

      {/* Disable flow */}
      {status.enabled && isSelf && (
        <Box>
          {!showDisable ? (
            <Button
              variant="outlined"
              color="error"
              onClick={() => setShowDisable(true)}
              disabled={status.enforced}
            >
              {status.enforced ? "Cannot disable (enforced)" : "Disable 2FA"}
            </Button>
          ) : (
            <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
              <TextField
                size="small"
                type="password"
                label="Confirm password"
                value={disablePassword}
                onChange={(e) => setDisablePassword(e.target.value)}
                sx={{ width: 220 }}
              />
              <LoadingButton variant="contained" color="error" loading={loading} onClick={handleDisable}>
                Confirm Disable
              </LoadingButton>
              <Button variant="outlined" onClick={() => { setShowDisable(false); setDisablePassword(""); }}>
                Cancel
              </Button>
            </Box>
          )}
        </Box>
      )}
    </Card>
  );
}
