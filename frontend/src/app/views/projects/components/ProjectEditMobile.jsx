import { useEffect, useState } from "react";
import {
  Box, Button, CircularProgress, Divider, FormControlLabel, Stack, Switch,
  Typography, Tooltip, IconButton, Chip,
} from "@mui/material";
import { Refresh, ContentCopy, PhoneAndroid, QrCode2 } from "@mui/icons-material";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

/**
 * Mobile integration tab.
 *
 * Toggle minting a read-only, project-scoped API key that mobile
 * companion apps (Android, iOS, …) can scan via QR. The plaintext key
 * is returned only once (on enable / regenerate); after that the UI
 * keeps it in memory until the user leaves the page so additional
 * phones can still be paired during the same session.
 */
export default function ProjectEditMobile({ project }) {
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null); // "enable" | "disable" | "regenerate" | null
  const [status, setStatus] = useState(null);
  // Plaintext QR payload. Only available immediately after enable/regenerate.
  const [qrPayload, setQrPayload] = useState(null);

  // Both GET /mobile and POST /mobile/{enable,regenerate} return the full
  // QR payload whenever the integration is enabled, so we always pick it up
  // from the server response (no need to cache plaintext client-side).
  const applyStatus = (res) => {
    setStatus(res);
    setQrPayload(res && res.qr ? res.qr : null);
  };

  useEffect(() => {
    let cancelled = false;
    api.get(`/projects/${project.id}/mobile`, auth.user.token, { silent: true })
      .then((r) => { if (!cancelled) { applyStatus(r); setLoading(false); } })
      .catch(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [project.id]);

  // Self-heal: if the server reports enabled but didn't hand us a QR
  // payload (stale/older backend), re-issue the idempotent enable call —
  // it will decrypt the existing key server-side and return it. No
  // phone is revoked by this; regenerate is what rotates.
  useEffect(() => {
    if (loading) return;
    const enabled = !!(status && status.enabled);
    if (!enabled || qrPayload || busy) return;
    setBusy("refresh");
    api.post(`/projects/${project.id}/mobile/enable`, {}, auth.user.token)
      .then(applyStatus)
      .catch(() => {})
      .finally(() => setBusy(null));
    // deps intentionally narrow so we only fire once per state transition
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, status && status.enabled, qrPayload]);

  const enable = () => {
    setBusy("enable");
    api.post(`/projects/${project.id}/mobile/enable`, {}, auth.user.token)
      .then(applyStatus)
      .catch(() => {})
      .finally(() => setBusy(null));
  };

  const disable = () => {
    if (!window.confirm("Turn off Mobile integration? Every paired phone will immediately lose access.")) return;
    setBusy("disable");
    api.post(`/projects/${project.id}/mobile/disable`, {}, auth.user.token)
      .then((r) => { applyStatus(r); setQrPayload(null); })
      .catch(() => {})
      .finally(() => setBusy(null));
  };

  const regenerate = () => {
    if (!window.confirm("Invalidate every currently-paired phone and show a fresh QR code?")) return;
    setBusy("regenerate");
    api.post(`/projects/${project.id}/mobile/regenerate`, {}, auth.user.token)
      .then(applyStatus)
      .catch(() => {})
      .finally(() => setBusy(null));
  };

  const copyPayload = () => {
    if (!qrPayload) return;
    navigator.clipboard.writeText(JSON.stringify(qrPayload));
    toast.success("Copied to clipboard");
  };

  if (loading) {
    return <Box sx={{ p: 3, display: "flex", justifyContent: "center" }}><CircularProgress size={24} /></Box>;
  }

  const enabled = !!(status && status.enabled);
  const qrText = qrPayload ? JSON.stringify(qrPayload) : null;

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
        <PhoneAndroid color="primary" />
        <Typography variant="h6" fontWeight={700}>Mobile integration</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Scan the QR code with the RESTai mobile app (Android today, more platforms
        coming) to get a read-only chat into this project. The app only ever uses
        chat mode (streaming). Toggle off or regenerate to revoke every paired
        phone at once.
      </Typography>

      <FormControlLabel
        control={
          <Switch
            checked={enabled}
            disabled={!!busy}
            onChange={(e) => (e.target.checked ? enable() : disable())}
          />
        }
        label={enabled ? "Enabled" : "Disabled"}
      />

      <Divider sx={{ my: 3 }} />

      {enabled ? (
        <Stack spacing={2} alignItems="flex-start">
          <Box
            sx={{
              p: 2, bgcolor: "#fff", borderRadius: 2, border: 1,
              borderColor: "divider", display: "inline-flex",
              alignItems: "center", justifyContent: "center",
              width: 252, height: 252,
            }}
          >
            {qrText ? (
              <QRCodeSVG value={qrText} size={220} includeMargin={false} level="M" />
            ) : (
              <CircularProgress size={32} />
            )}
          </Box>
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            {status.key_prefix && (
              <Chip
                icon={<QrCode2 />}
                label={`key ${status.key_prefix}…`}
                size="small"
                variant="outlined"
              />
            )}
            <Tooltip title="Copy raw payload (JSON)">
              <span>
                <IconButton size="small" onClick={copyPayload} disabled={!qrPayload}>
                  <ContentCopy fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Button
              size="small"
              variant="outlined"
              color="warning"
              startIcon={<Refresh />}
              disabled={busy === "regenerate"}
              onClick={regenerate}
            >
              {busy === "regenerate" ? "Regenerating…" : "Regenerate key"}
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 360 }}>
            Show this QR to as many phones as you like — every one of them
            shares the same read-only key. Click <b>Regenerate key</b> to
            invalidate every paired phone in one go.
          </Typography>
        </Stack>
      ) : (
        <Typography variant="body2" color="text.secondary">
          Mobile integration is off. No API key exists for mobile apps on this project.
        </Typography>
      )}
    </Box>
  );
}
