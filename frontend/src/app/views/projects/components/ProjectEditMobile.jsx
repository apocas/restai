import { useEffect, useState } from "react";
import {
  Box, Button, CircularProgress, Divider, FormControlLabel, Stack, Switch,
  Typography, Tooltip, IconButton, Chip,
} from "@mui/material";
import { Refresh, ContentCopy, PhoneAndroid, QrCode2 } from "@mui/icons-material";
import { QRCodeSVG } from "qrcode.react";
import { toast } from "react-toastify";
import { useTranslation, Trans } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import ContentCard from "app/components/page/ContentCard";

export default function ProjectEditMobile({ project }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null); // "enable" | "disable" | "regenerate" | null
  const [status, setStatus] = useState(null);
  const [qrPayload, setQrPayload] = useState(null);

  // GET /mobile and POST /mobile/{enable,regenerate} both return the QR
  // payload while enabled, so we never cache plaintext client-side.
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

  // Self-heal: server reports enabled but no QR payload (stale backend) —
  // re-issue idempotent enable to decrypt the existing key. Does NOT revoke.
  useEffect(() => {
    if (loading) return;
    const enabled = !!(status && status.enabled);
    if (!enabled || qrPayload || busy) return;
    setBusy("refresh");
    api.post(`/projects/${project.id}/mobile/enable`, {}, auth.user.token)
      .then(applyStatus)
      .catch(() => {})
      .finally(() => setBusy(null));
    // Deps narrow so we only fire once per state transition.
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
    toast.success(t("common.copied"));
  };

  if (loading) {
    return <Box sx={{ p: 3, display: "flex", justifyContent: "center" }}><CircularProgress size={24} /></Box>;
  }

  const enabled = !!(status && status.enabled);
  const qrText = qrPayload ? JSON.stringify(qrPayload) : null;

  return (
    <ContentCard
      icon={<PhoneAndroid />}
      title={t("projects.edit.mobile.title")}
      subtitle={`PROJECT/${String(project.id).padStart(4, "0")} · COMPANION · QR PAIR`}
    >
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        {t("projects.edit.mobile.intro")}
      </Typography>

      <FormControlLabel
        control={
          <Switch
            checked={enabled}
            disabled={!!busy}
            onChange={(e) => (e.target.checked ? enable() : disable())}
          />
        }
        label={enabled ? t("common.enabled") : t("common.disabled")}
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
          {status?.host && (
            <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 360 }}>
              {t("projects.edit.mobile.openLink", { url: `${status.host}/mobile` })}
            </Typography>
          )}
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            {status.key_prefix && (
              <Chip
                icon={<QrCode2 />}
                label={t("projects.edit.mobile.keyChip", { prefix: status.key_prefix })}
                size="small"
                variant="outlined"
              />
            )}
            <Tooltip title={t("projects.edit.mobile.copyPayload")}>
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
              {busy === "regenerate" ? t("projects.edit.mobile.regenerating") : t("projects.edit.mobile.regenerate")}
            </Button>
          </Stack>
          <Typography variant="caption" color="text.secondary" sx={{ maxWidth: 360 }}>
            <Trans i18nKey="projects.edit.mobile.hint" components={{ 1: <b /> }} />
          </Typography>
        </Stack>
      ) : (
        <Typography variant="body2" color="text.secondary">
          {t("projects.edit.mobile.offMessage")}
        </Typography>
      )}
    </ContentCard>
  );
}
