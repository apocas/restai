import { Alert, Button, Divider, Grid, TextField, Typography } from "@mui/material";
import { Fragment, useState } from "react";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";

export default function ProjectEditIntegrations({ state, setState, handleChange, project }) {
  const auth = useAuth();
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);

  // Webhook URL the admin pastes into Meta Business Suite. Read-only.
  // Falls back to window.location.origin when REACT_APP_RESTAI_API_URL
  // isn't set so dev installs still get a copyable value.
  const apiBase = (process.env.REACT_APP_RESTAI_API_URL || window.location.origin).replace(/\/$/, "");
  const webhookUrl = `${apiBase}/webhooks/whatsapp`;

  const setOpt = (key) => (e) => setState({ ...state, options: { ...state.options, [key]: e.target.value } });

  const onTestConnection = () => {
    if (!project?.id) return;
    setTesting(true);
    setTestResult(null);
    api.post(`/projects/${project.id}/whatsapp/test`, {}, auth.user.token)
      .then((res) => setTestResult(res.data))
      .catch((err) => setTestResult({ ok: false, error: err?.response?.data?.detail || err.message || "request failed" }))
      .finally(() => setTesting(false));
  };

  return (
    <Grid container spacing={3}>
      {(state.type === "rag" || state.type === "agent") && (
        <Fragment>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              name="telegram_token"
              label="Telegram Bot Token"
              type="password"
              variant="outlined"
              onChange={handleChange}
              value={state.options?.telegram_token ?? ''}
              helperText="Paste the token from @BotFather to connect this project to Telegram"
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              type="number"
              name="telegram_default_chat_id"
              label="Default Telegram Chat ID"
              variant="outlined"
              value={state.options?.telegram_default_chat_id ?? ''}
              onChange={(e) => setState({
                ...state,
                options: {
                  ...state.options,
                  telegram_default_chat_id: e.target.value ? parseInt(e.target.value) : null,
                },
              })}
              helperText="Outbound chat for the send_telegram tool. Send /chatid to the bot in Telegram to find the value (works in DMs and groups)."
            />
          </Grid>
          <Grid item sm={12} xs={12}>
            <TextField
              fullWidth
              multiline
              minRows={2}
              InputLabelProps={{ shrink: true }}
              name="telegram_allowed_chat_ids"
              label="Allowed Telegram Chat IDs (inbound)"
              variant="outlined"
              value={state.options?.telegram_allowed_chat_ids ?? ''}
              onChange={(e) => setState({
                ...state,
                options: {
                  ...state.options,
                  telegram_allowed_chat_ids: e.target.value,
                },
              })}
              placeholder="123456789, -1001234567890"
              helperText="Comma-separated. Only these chats may talk to the bot — anyone else gets a polite 'not authorized' reply. Leave empty to let anyone who finds the bot chat with it (default). The /chatid command stays open so unauthorized users can find their id and ask the admin to add them."
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              name="slack_bot_token"
              label="Slack Bot Token"
              type="password"
              variant="outlined"
              onChange={(e) => setState({ ...state, options: { ...state.options, slack_bot_token: e.target.value } })}
              value={state.options?.slack_bot_token ?? ''}
              helperText="Bot token (xoxb-...) from your Slack app"
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              name="slack_app_token"
              label="Slack App Token"
              type="password"
              variant="outlined"
              onChange={(e) => setState({ ...state, options: { ...state.options, slack_app_token: e.target.value } })}
              value={state.options?.slack_app_token ?? ''}
              helperText="App token (xapp-...) for Socket Mode -- create at api.slack.com"
            />
          </Grid>

          <Grid item xs={12}>
            <Divider sx={{ my: 1 }}>
              <Typography variant="overline" color="text.secondary">WhatsApp Business Cloud API</Typography>
            </Divider>
          </Grid>

          <Grid item xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="Webhook URL (paste into Meta Business Suite)"
              variant="outlined"
              value={webhookUrl}
              InputProps={{ readOnly: true }}
              helperText="Configure this URL in Meta Business Suite → WhatsApp → Configuration → Webhooks. Use the verify token below as the 'Verify token' field. Routing is by phone_number_id, so one URL serves every project on this instance."
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="Phone Number ID"
              variant="outlined"
              value={state.options?.whatsapp_phone_number_id ?? ''}
              onChange={setOpt("whatsapp_phone_number_id")}
              helperText="Long numeric id from Meta Business Suite → WhatsApp → API Setup. Used to route inbound messages to this project."
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="Default Recipient (E.164, no '+')"
              variant="outlined"
              value={state.options?.whatsapp_default_to ?? ''}
              onChange={setOpt("whatsapp_default_to")}
              placeholder="351912345678"
              helperText="Destination phone for the send_whatsapp tool. Constrained by Meta's 24h customer-service window — the recipient must have messaged the bot in the last 24 hours."
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="Access Token"
              type="password"
              variant="outlined"
              value={state.options?.whatsapp_access_token ?? ''}
              onChange={setOpt("whatsapp_access_token")}
              helperText="Long-lived System User token from Meta Business Suite. Encrypted at rest."
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="App Secret"
              type="password"
              variant="outlined"
              value={state.options?.whatsapp_app_secret ?? ''}
              onChange={setOpt("whatsapp_app_secret")}
              helperText="Meta App secret — verifies the X-Hub-Signature-256 header on inbound webhooks. Encrypted at rest."
            />
          </Grid>
          <Grid item sm={6} xs={12}>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              label="Verify Token"
              type="password"
              variant="outlined"
              value={state.options?.whatsapp_verify_token ?? ''}
              onChange={setOpt("whatsapp_verify_token")}
              helperText="Any string you choose — Meta echoes it back during the initial webhook subscription handshake. Encrypted at rest."
            />
          </Grid>
          <Grid item sm={6} xs={12} sx={{ display: "flex", alignItems: "center" }}>
            <Button
              variant="outlined"
              onClick={onTestConnection}
              disabled={testing || !project?.id || !state.options?.whatsapp_phone_number_id || !state.options?.whatsapp_access_token}
            >
              {testing ? "Testing…" : "Test Connection"}
            </Button>
          </Grid>
          {testResult && (
            <Grid item xs={12}>
              <Alert severity={testResult.ok ? "success" : "error"}>
                {testResult.ok
                  ? `OK — display: ${testResult.display_name || "(none)"}, verified: ${testResult.verified_name || "(none)"}, quality: ${testResult.quality_rating || "n/a"}`
                  : `Error: ${testResult.error || "unknown failure"}`}
              </Alert>
            </Grid>
          )}
          <Grid item xs={12}>
            <TextField
              fullWidth
              multiline
              minRows={2}
              InputLabelProps={{ shrink: true }}
              label="Allowed Sender Phone Numbers (inbound, E.164, no '+')"
              variant="outlined"
              value={state.options?.whatsapp_allowed_phone_numbers ?? ''}
              onChange={setOpt("whatsapp_allowed_phone_numbers")}
              placeholder="351912345678, 14155551234"
              helperText="Comma-separated. Only these senders may chat with the bot — anyone else gets a polite 'not authorized' reply. Leave empty for open access (NOT recommended for production — protects your WhatsApp number quality rating from spam)."
            />
          </Grid>
        </Fragment>
      )}
    </Grid>
  );
}
