import { Grid, TextField, Button, Switch, Slider, Autocomplete, Typography, IconButton, Divider, Box, CircularProgress } from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import FormControlLabel from "@mui/material/FormControlLabel";
import { Fragment } from "react";

export default function ProjectEditIntegrations({ state, setState, handleChange, project, mcpServers, setMcpServers, tools, handleAddMcpServer, handleRemoveMcpServer, handleMcpServerFieldChange, handleProbeMcpServer, handleMcpToolsChange, isStdioServer }) {
  return (
    <Grid container spacing={3}>
      {(state.type === "rag" || state.type === "inference" || state.type === "agent") && (
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

      {state.type === "agent" && (
        <Fragment>
          <Grid item sm={12} xs={12}>
            <Divider sx={{ mb: 1 }} />
          </Grid>
          <Grid item sm={6} xs={12}>
            <Autocomplete
              multiple
              options={tools.map((tool) => tool.name)}
              getOptionLabel={(option) => option}
              isOptionEqualToValue={(option, value) => option === value}
              onChange={(event, newValue) => {
                setState({
                  ...state,
                  options: {
                    ...state.options,
                    tools: newValue.join(",")
                  }
                });
              }}
              value={state.options?.tools ? state.options.tools.split(",").filter(tool => tool.trim() !== "") : []}
              renderInput={(params) => (
                <TextField
                  {...params}
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  label="Tools"
                  variant="outlined"
                />
              )}
            />
          </Grid>
          <Grid item sm={12} xs={12}>
            <Divider sx={{ mb: 1 }} />
          </Grid>
          <Grid item sm={12} xs={12}>
            <Typography variant="subtitle1" gutterBottom>MCP Servers</Typography>
            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 2 }}>
              Connect to external tool servers using the MCP protocol. Two connection modes are supported:
              <br />
              <strong>HTTP/SSE</strong> — enter a URL (e.g. <code>http://localhost:3001/sse</code> or <code>http://localhost:8000/mcp</code>)
              <br />
              <strong>Stdio</strong> — enter a command (e.g. <code>npx</code>, <code>python</code>, <code>uvx</code>) and its arguments below (e.g. <code>-y @modelcontextprotocol/server-filesystem /tmp</code>)
            </Typography>
            {mcpServers.map((server, index) => (
              <Box key={index} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0', borderRadius: 1 }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <TextField
                    fullWidth
                    size="small"
                    label={isStdioServer(server.host) ? "Command" : "URL or Command"}
                    placeholder="http://localhost:3001/sse or npx"
                    value={server.host}
                    onChange={(e) => handleMcpServerFieldChange(index, 'host', e.target.value)}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    disabled={!server.host.trim() || server.loading}
                    onClick={() => handleProbeMcpServer(index)}
                    sx={{ minWidth: 80 }}
                  >
                    {server.loading ? <CircularProgress size={20} /> : "Check"}
                  </Button>
                  <IconButton size="small" onClick={() => handleRemoveMcpServer(index)}>
                    <DeleteIcon />
                  </IconButton>
                </Box>
                {isStdioServer(server.host) && (
                  <Box sx={{ mb: 1 }}>
                    <TextField
                      fullWidth
                      size="small"
                      label="Arguments"
                      placeholder="-y @modelcontextprotocol/server-filesystem /tmp"
                      helperText="Space-separated arguments passed to the command"
                      value={(server.args || []).join(" ")}
                      onChange={(e) => {
                        const val = e.target.value;
                        handleMcpServerFieldChange(index, 'args', val ? val.split(" ").filter(a => a !== "") : []);
                      }}
                      sx={{ mb: 1 }}
                    />
                    <TextField
                      fullWidth
                      size="small"
                      label="Environment Variables"
                      placeholder="KEY=value ANOTHER=value"
                      helperText="Space-separated KEY=value pairs (e.g. PORT=3001 DEBUG=true)"
                      value={Object.entries(server.env || {}).map(([k, v]) => `${k}=${v}`).join(" ")}
                      onChange={(e) => {
                        const val = e.target.value;
                        const env = {};
                        if (val) {
                          val.split(" ").filter(p => p.includes("=")).forEach(pair => {
                            const eqIdx = pair.indexOf("=");
                            env[pair.substring(0, eqIdx)] = pair.substring(eqIdx + 1);
                          });
                        }
                        handleMcpServerFieldChange(index, 'env', env);
                      }}
                    />
                  </Box>
                )}
                {server.error && (
                  <Typography variant="body2" color="error" sx={{ mb: 1 }}>{server.error}</Typography>
                )}
                {server.availableTools.length > 0 && (
                  <Autocomplete
                    multiple
                    freeSolo
                    size="small"
                    options={server.availableTools.map(t => t.name)}
                    value={server.tools ? server.tools.split(",").map(t => t.trim()).filter(t => t !== "") : []}
                    onChange={(e, newValue) => handleMcpToolsChange(index, newValue)}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="Tools (leave empty for all)"
                        variant="outlined"
                        helperText={`${server.availableTools.length} tool(s) available`}
                      />
                    )}
                  />
                )}
              </Box>
            ))}
            <Button variant="outlined" size="small" onClick={handleAddMcpServer}>
              Add MCP Server
            </Button>
          </Grid>
        </Fragment>
      )}

    </Grid>
  );
}
