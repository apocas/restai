import { Grid, TextField } from "@mui/material";
import { Fragment } from "react";

export default function ProjectEditIntegrations({ state, setState, handleChange }) {
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
              helperText="Where the send_telegram tool posts. Send /chatid to the bot in Telegram to find the value (works in DMs and groups)."
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
        </Fragment>
      )}
    </Grid>
  );
}
