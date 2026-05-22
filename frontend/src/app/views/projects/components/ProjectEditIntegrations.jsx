import { Alert, Box, Button, Typography } from "@mui/material";
import { Hub, PlayArrow } from "@mui/icons-material";
import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";
import ContentCard from "app/components/page/ContentCard";
import ProjectEditWebhooks from "./ProjectEditWebhooks";
import {
  CopyButton, MonoField, SecretField, SectionHeader,
  sectionLabelSx, sectionShellSx,
} from "./integrationsKit";

const TG_ACCENT  = "#229ED9";
const SK_ACCENT  = "#E01E5A";
const WA_ACCENT  = "#25D366";
const SMTP_ACCENT = "#0ea5e9";
const SMS_ACCENT  = "#F22F46";

function Section({ accent, children }) {
  return (
    <Box sx={{ ...sectionShellSx(accent), p: 2.5, display: "flex", flexDirection: "column", gap: 2 }}>
      {children}
    </Box>
  );
}

function FieldGrid({ children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
      {children}
    </Box>
  );
}

export default function ProjectEditIntegrations({ state, setState, project }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [waTest, setWaTest] = useState(null);
  const [waTesting, setWaTesting] = useState(false);

  const apiBase = (process.env.REACT_APP_RESTAI_API_URL || window.location.origin).replace(/\/$/, "");
  const inboundWhatsappUrl = `${apiBase}/webhooks/whatsapp`;

  const setOpt = (key) => (e) => setState({ ...state, options: { ...state.options, [key]: e.target.value } });
  const setOptVal = (key, value) => setState({ ...state, options: { ...state.options, [key]: value } });

  const opts = state.options || {};

  const tgLive = !!(opts.telegram_token && String(opts.telegram_token).trim());
  const skLive = !!(opts.slack_bot_token && String(opts.slack_bot_token).trim());
  const waLive = !!(opts.whatsapp_phone_number_id && opts.whatsapp_access_token);
  const smtpLive = !!(opts.smtp_host && String(opts.smtp_host).trim());
  const smsLive = !!(opts.twilio_account_sid && opts.twilio_auth_token && opts.twilio_from_number);

  const onWhatsappTest = () => {
    if (!project?.id) return;
    setWaTesting(true);
    setWaTest(null);
    api.post(`/projects/${project.id}/whatsapp/test`, {}, auth.user.token)
      .then((res) => setWaTest({ ...(res.data || res) }))
      .catch((err) => setWaTest({ ok: false, error: err?.response?.data?.detail || err.message || "request failed" }))
      .finally(() => setWaTesting(false));
  };

  if (state.type !== "rag" && !state.type === "agent") {
    return (
      <ContentCard
        icon={<Hub />}
        title="Integrations"
        subtitle={`PROJECT/${String(project?.id ?? 0).padStart(4, "0")}`}
      >
        <Typography variant="body2" color="text.secondary">
          Integrations are available for RAG and Agent projects only.
        </Typography>
      </ContentCard>
    );
  }

  return (
    <ContentCard
      icon={<Hub />}
      title="Integrations"
      subtitle={`PROJECT/${String(project?.id ?? 0).padStart(4, "0")} · TELEGRAM · SLACK · WHATSAPP · EMAIL · SMS · WEBHOOKS`}
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>

        {/* ── TELEGRAM ──────────────────────────────────────── */}
        <Section accent={TG_ACCENT}>
          <SectionHeader
            title="Telegram"
            live={tgLive}
            accent={TG_ACCENT}
            subtitle="Bot token + optional outbound chat target."
          />
          <FieldGrid>
            <SecretField
              label={t("projects.edit.integrations.telegramToken", "Bot token")}
              value={opts.telegram_token}
              onChange={setOpt("telegram_token")}
              helper="From @BotFather. Encrypted at rest."
            />
            <MonoField
              label={t("projects.edit.integrations.telegramDefaultChatId", "Default chat id")}
              type="number"
              value={opts.telegram_default_chat_id}
              onChange={(e) => setOptVal("telegram_default_chat_id", e.target.value ? parseInt(e.target.value) : null)}
              placeholder="123456789"
              helper="Outbound target for the send_telegram tool. Send /chatid to the bot to find it."
            />
          </FieldGrid>
          <MonoField
            label={t("projects.edit.integrations.telegramAllowedChatIds", "Allowed chat ids (CSV)")}
            multiline
            rows={2}
            value={opts.telegram_allowed_chat_ids}
            onChange={(e) => setOptVal("telegram_allowed_chat_ids", e.target.value)}
            placeholder="123456789, -1001234567890"
            helper="Only these chats may talk to the bot. Empty = open. /chatid stays available so unauthorized users can find their id."
          />
        </Section>

        {/* ── SLACK ─────────────────────────────────────────── */}
        <Section accent={SK_ACCENT}>
          <SectionHeader
            title="Slack"
            live={skLive}
            accent={SK_ACCENT}
            subtitle="Cron-poller — checks for new messages every minute."
          />
          <FieldGrid>
            <SecretField
              label={t("projects.edit.integrations.slackBotToken", "Bot token (xoxb-…)")}
              value={opts.slack_bot_token}
              onChange={(e) => setOptVal("slack_bot_token", e.target.value)}
              helper="From your Slack app's OAuth & Permissions page."
            />
            <SecretField
              label={t("projects.edit.integrations.slackAppToken", "App token (xapp-…)")}
              value={opts.slack_app_token}
              onChange={(e) => setOptVal("slack_app_token", e.target.value)}
              helper="Optional — only needed for legacy Socket Mode setups."
            />
          </FieldGrid>
        </Section>

        {/* ── WHATSAPP ──────────────────────────────────────── */}
        <Section accent={WA_ACCENT}>
          <SectionHeader
            title="WhatsApp Business Cloud"
            live={waLive}
            accent={WA_ACCENT}
            subtitle="Routed by phone_number_id — one URL serves every project."
          />
          <MonoField
            label={t("projects.edit.integrations.webhookUrl", "Inbound webhook URL")}
            value={inboundWhatsappUrl}
            readOnly
            right={<CopyButton value={inboundWhatsappUrl} />}
            helper="Paste this in Meta Business Suite → WhatsApp → Configuration → Webhooks. Use the Verify Token below as the 'Verify token' field."
          />
          <FieldGrid>
            <MonoField
              label={t("projects.edit.integrations.phoneNumberId", "Phone Number ID")}
              value={opts.whatsapp_phone_number_id}
              onChange={setOpt("whatsapp_phone_number_id")}
              placeholder="100000000000000"
              helper="From Meta Business Suite → WhatsApp → API Setup."
            />
            <MonoField
              label={t("projects.edit.integrations.defaultRecipient", "Default recipient")}
              value={opts.whatsapp_default_to}
              onChange={setOpt("whatsapp_default_to")}
              placeholder="351912345678"
              helper="Outbound target for send_whatsapp. Subject to Meta's 24h customer-service window."
            />
            <SecretField
              label={t("projects.edit.integrations.accessToken", "Access Token")}
              value={opts.whatsapp_access_token}
              onChange={setOpt("whatsapp_access_token")}
              helper="Long-lived System User token. Encrypted at rest."
            />
            <SecretField
              label={t("projects.edit.integrations.appSecret", "App Secret")}
              value={opts.whatsapp_app_secret}
              onChange={setOpt("whatsapp_app_secret")}
              helper="Verifies inbound X-Hub-Signature-256. Encrypted at rest."
            />
            <SecretField
              label={t("projects.edit.integrations.verifyToken", "Verify Token")}
              value={opts.whatsapp_verify_token}
              onChange={setOpt("whatsapp_verify_token")}
              helper="Any string you choose — Meta echoes it back during the subscription handshake."
            />
            <Box sx={{ display: "flex", alignItems: "flex-end" }}>
              <Button
                variant="outlined"
                onClick={onWhatsappTest}
                disabled={waTesting || !project?.id || !opts.whatsapp_phone_number_id || !opts.whatsapp_access_token}
                startIcon={<PlayArrow />}
              >
                {waTesting
                  ? t("projects.edit.integrations.testing", "Testing…")
                  : t("projects.edit.integrations.testConnection", "Test connection")}
              </Button>
            </Box>
          </FieldGrid>
          <MonoField
            label={t("projects.edit.integrations.allowedPhoneNumbers", "Allowed sender phone numbers (CSV)")}
            multiline
            rows={2}
            value={opts.whatsapp_allowed_phone_numbers}
            onChange={setOpt("whatsapp_allowed_phone_numbers")}
            placeholder="351912345678, 14155551234"
            helper="E.164. Empty = open access (NOT recommended in production — protects your number's quality rating from spam)."
          />
          {waTest && (
            <Alert severity={waTest.ok ? "success" : "error"} sx={{ fontFamily: "inherit", fontSize: "0.82rem" }}>
              {waTest.ok
                ? `OK · display: ${waTest.display_name || "(none)"} · verified: ${waTest.verified_name || "(none)"} · quality: ${waTest.quality_rating || "n/a"}`
                : `Error: ${waTest.error || "unknown failure"}`}
            </Alert>
          )}
        </Section>

        {/* ── EMAIL / SMTP ──────────────────────────────────── */}
        <Section accent={SMTP_ACCENT}>
          <SectionHeader
            title="Email · SMTP"
            live={smtpLive}
            accent={SMTP_ACCENT}
            subtitle="Used by the send_email tool. Any SMTP relay (Gmail, SES, Mailgun, your own postfix)."
          />
          <FieldGrid>
            <MonoField
              label={t("projects.edit.integrations.smtpHost", "SMTP Host")}
              value={opts.smtp_host}
              onChange={setOpt("smtp_host")}
              placeholder="smtp.gmail.com"
            />
            <MonoField
              label={t("projects.edit.integrations.smtpPort", "Port")}
              type="number"
              value={opts.smtp_port ?? 587}
              onChange={setOpt("smtp_port")}
              placeholder="587"
              helper="587 STARTTLS · 465 implicit TLS · 25 plaintext."
            />
            <MonoField
              label={t("projects.edit.integrations.smtpUsername", "Username")}
              value={opts.smtp_user}
              onChange={setOpt("smtp_user")}
            />
            <SecretField
              label={t("projects.edit.integrations.smtpPassword", "Password")}
              value={opts.smtp_password}
              onChange={setOpt("smtp_password")}
              helper="Encrypted at rest."
            />
            <MonoField
              label={t("projects.edit.integrations.fromAddress", "From address")}
              value={opts.smtp_from}
              onChange={setOpt("smtp_from")}
              placeholder="Bot <bot@example.com>"
            />
            <MonoField
              label={t("projects.edit.integrations.defaultRecipient", "Default recipient")}
              value={opts.email_default_to}
              onChange={setOpt("email_default_to")}
              placeholder="you@example.com"
              helper="Where send_email delivers — typically your own inbox."
            />
          </FieldGrid>
        </Section>

        {/* ── SMS / TWILIO ──────────────────────────────────── */}
        <Section accent={SMS_ACCENT}>
          <SectionHeader
            title="SMS · Twilio"
            live={smsLive}
            accent={SMS_ACCENT}
            subtitle="Used by the send_sms tool. Twilio REST + basic auth."
          />
          <FieldGrid>
            <MonoField
              label={t("projects.edit.integrations.twilioSid", "Account SID")}
              value={opts.twilio_account_sid}
              onChange={setOpt("twilio_account_sid")}
              placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            />
            <SecretField
              label={t("projects.edit.integrations.twilioToken", "Auth Token")}
              value={opts.twilio_auth_token}
              onChange={setOpt("twilio_auth_token")}
              helper="Encrypted at rest."
            />
            <MonoField
              label={t("projects.edit.integrations.twilioFrom", "From number (E.164)")}
              value={opts.twilio_from_number}
              onChange={setOpt("twilio_from_number")}
              placeholder="+15551234567"
              helper="A number you've provisioned in Twilio."
            />
            <MonoField
              label={t("projects.edit.integrations.defaultRecipient", "Default recipient")}
              value={opts.sms_default_to}
              onChange={setOpt("sms_default_to")}
              placeholder="+351912345678"
              helper="Where send_sms delivers — typically your own phone."
            />
          </FieldGrid>
        </Section>

        {/* ── WEBHOOKS ──────────────────────────────────────── */}
        <Box>
          <Box sx={{ ...sectionLabelSx, mb: 1 }}>
            {t("projects.edit.integrations.webhooks", "Outbound event webhooks")}
          </Box>
          <ProjectEditWebhooks state={state} setState={setState} project={project} />
        </Box>

      </Box>
    </ContentCard>
  );
}
