import {
  Grid, TextField, MenuItem, Switch, Slider, Autocomplete, Divider, Typography, Button, Box, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress, Alert,
} from "@mui/material";
import { HelpOutline, AutoAwesome } from "@mui/icons-material";
import FormControlLabel from "@mui/material/FormControlLabel";
import { Fragment, useState } from "react";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const HelpTip = ({ text }) => (
  <Tooltip title={text} placement="top" arrow>
    <HelpOutline sx={{ fontSize: 16, color: "text.disabled", ml: 0.5, cursor: "help", verticalAlign: "middle" }} />
  </Tooltip>
);

export default function ProjectEditGeneral({ state, setState, handleChange, project, info, users, teams, promptVersions, showVersions, setShowVersions, handleTeamChange }) {
  const auth = useAuth();
  const [aiOpen, setAiOpen] = useState(false);
  const [aiDescription, setAiDescription] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const handleGeneratePrompt = () => {
    if (!aiDescription.trim()) return;
    setAiLoading(true);
    api.post(
      `/projects/${project.id}/system-prompt/generate`,
      { description: aiDescription, project_type: state.type || project.type },
      auth.user.token,
    )
      .then((d) => {
        setState((prev) => ({ ...prev, system: d.system_prompt || "" }));
        toast.success("System prompt generated");
        setAiOpen(false);
        setAiDescription("");
      })
      .catch(() => {})
      .finally(() => setAiLoading(false));
  };

  return (
    <Fragment>
    <Grid container spacing={3}>
      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="human_name"
          label="Project Human Name"
          variant="outlined"
          onChange={handleChange}
          value={state.human_name ?? ''}
        />
      </Grid>

      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="human_description"
          label="Project Human Description"
          variant="outlined"
          onChange={handleChange}
          value={state.human_description ?? ''}
        />
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>

      {state.public !== undefined && (
        <Grid item sm={6} xs={12}>
          <FormControlLabel
            label={<span>Shared<HelpTip text="When enabled, all users on the platform can access this project" /></span>}
            control={
              <Switch
                checked={state.public}
                name="public"
                inputProps={{ "aria-label": "secondary checkbox controlled" }}
                onChange={handleChange}
              />
            }
          />
        </Grid>
      )}

      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label={<span>Logging<HelpTip text="Records all requests and responses for analytics and debugging" /></span>}
          control={
            <Switch
              checked={state.options?.logging ?? false}
              name="logging"
              inputProps={{ "aria-label": "logging checkbox" }}
              onChange={handleChange}
            />
          }
        />
      </Grid>

      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label={<span>Redact secrets in logs<HelpTip text="Strip API keys, tokens and credentials from question/answer/system prompt before persisting" /></span>}
          control={
            <Switch
              checked={state.options?.redact_inference_logs ?? false}
              name="redact_inference_logs"
              inputProps={{ "aria-label": "redact inference logs checkbox" }}
              onChange={handleChange}
              disabled={!(state.options?.logging ?? false)}
            />
          }
        />
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>

      <Grid item sm={12} xs={12}>
        <Autocomplete
          multiple
          id="users-select"
          options={users}
          getOptionLabel={(option) => option.username}
          value={state.selectedUsers || []}
          isOptionEqualToValue={(option, value) => option.username === value.username}
          onChange={(event, newValue) => {
            setState({ ...state, selectedUsers: newValue });
          }}
          renderInput={(params) => (
            <TextField
              {...params}
              variant="outlined"
              label="Users with access"
              placeholder="Select users"
            />
          )}
        />
        <Typography variant="caption" color="textSecondary">
          Select users who should have access to this project
        </Typography>
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>

      <Grid item sm={6} xs={12}>
        <TextField
          select
          fullWidth
          name="team_id"
          label="Team"
          variant="outlined"
          onChange={handleTeamChange}
          value={state.team ? state.team.id : (project.team ? project.team.id : '')}
        >
          {teams.map((team) => (
            <MenuItem value={team.id} key={team.id}>
              {team.name}
            </MenuItem>
          ))}
        </TextField>
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>

      {state.llm !== undefined && state.type !== "block" && (
        <Grid item sm={6} xs={12}>
          <TextField
            fullWidth
            select
            name="llm"
            label="LLM"
            variant="outlined"
            onChange={handleChange}
            value={state.llm ?? ''}
            defaultValue={state.llm ?? ''}
          >
            {info.llms
              .filter(item => {
                if (!state.team) return true;
                const teamLLMs = state.team.llms || [];
                const teamLLMNames = teamLLMs.map(llm => typeof llm === 'string' ? llm : llm.name);
                return teamLLMNames.includes(item.name);
              })
              .map((item) => (
                <MenuItem value={item.name} key={item.name}>
                  {item.name}
                </MenuItem>
              ))}
          </TextField>
        </Grid>
      )}

      {(state.type === "rag" || state.type === "agent") && (
        <Fragment>
          <Grid item sm={12} xs={12}>
            <Divider sx={{ mb: 1 }} />
          </Grid>
          <Grid item sm={12} xs={12}>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Typography variant="subtitle1" gutterBottom>System Message</Typography>
              {info?.system_llm_configured && (
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<AutoAwesome />}
                  onClick={() => setAiOpen(true)}
                >
                  Generate with AI
                </Button>
              )}
            </Box>
            <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
              Defines the AI's behavior and personality. This is prepended to every conversation.
            </Typography>
            <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap', mb: 1 }}>
              <Button size="small" variant="outlined" onClick={() => setState({ ...state, system: "You are a helpful assistant. Answer questions clearly and concisely." })}>
                General Assistant
              </Button>
              <Button size="small" variant="outlined" onClick={() => setState({ ...state, system: "Describe the provided image in detail. Include colors, objects, people, text, and any notable features." })}>
                Describe Image
              </Button>
              <Button size="small" variant="outlined" onClick={() => setState({ ...state, system: "Summarize the following text. Keep the summary concise while preserving the key points and main ideas." })}>
                Summarize Text
              </Button>
              <Button size="small" variant="outlined" onClick={() => setState({ ...state, system: "You are a translator. Translate the user's input to English. Preserve the original meaning and tone." })}>
                Translate to English
              </Button>
              <Button size="small" variant="outlined" onClick={() => setState({ ...state, system: "Extract structured data from the user's input. Return the result as valid JSON." })}>
                Extract Data (JSON)
              </Button>
              <Button size="small" variant="outlined" onClick={() => setState({ ...state, system: "You are a code assistant. Help the user write, debug, and explain code. Use markdown code blocks in your responses." })}>
                Code Assistant
              </Button>
            </Box>
            <TextField
              fullWidth
              InputLabelProps={{ shrink: true }}
              name="system"
              label="System Message"
              variant="outlined"
              onChange={handleChange}
              value={state.system ?? ''}
              multiline
              minRows={3}
              maxRows={12}
            />
            {promptVersions.length > 0 && (
              <Box sx={{ mt: 2 }}>
                <Typography
                  variant="subtitle2"
                  sx={{ cursor: "pointer", display: "flex", alignItems: "center" }}
                  onClick={() => setShowVersions(!showVersions)}
                >
                  Version History ({promptVersions.length})
                  {showVersions ? " \u25B2" : " \u25BC"}
                </Typography>
                {showVersions && (
                  <Box sx={{ mt: 1, maxHeight: 300, overflow: "auto", border: "1px solid #e0e0e0", borderRadius: 1 }}>
                    {promptVersions.map((v) => (
                      <Box
                        key={v.id}
                        sx={{
                          p: 1,
                          borderBottom: "1px solid #f0f0f0",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          backgroundColor: v.is_active ? "#f0f7ff" : "transparent",
                        }}
                      >
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="body2">
                            <strong>v{v.version}</strong>
                            {v.is_active && <span style={{ color: "#1976d2", marginLeft: 8 }}>(active)</span>}
                            <span style={{ color: "#999", marginLeft: 8 }}>
                              {v.created_at ? new Date(v.created_at).toLocaleString() : ""}
                            </span>
                          </Typography>
                          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                            {v.system_prompt ? v.system_prompt.substring(0, 100) + (v.system_prompt.length > 100 ? "..." : "") : "(empty)"}
                          </Typography>
                        </Box>
                        {!v.is_active && (
                          <Button
                            size="small"
                            variant="outlined"
                            sx={{ ml: 1, minWidth: 70 }}
                            onClick={() => {
                              setState({ ...state, system: v.system_prompt });
                            }}
                          >
                            Restore
                          </Button>
                        )}
                      </Box>
                    ))}
                  </Box>
                )}
              </Box>
            )}
          </Grid>
        </Fragment>
      )}

      <Grid item sm={6} xs={12}>
        <TextField
          fullWidth
          InputLabelProps={{ shrink: true }}
          name="default_prompt"
          label="Default Prompt"
          variant="outlined"
          onChange={handleChange}
          value={state.default_prompt ?? ''}
        />
      </Grid>

      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>
      <Grid item sm={6} xs={12}>
        <FormControlLabel
          label={<span>Cache<HelpTip text="Caches similar questions to avoid redundant LLM calls, reducing cost and latency" /></span>}
          control={
            <Switch
              checked={state.options?.cache ?? false}
              name="cache"
              inputProps={{ "aria-label": "cache checkbox" }}
              onChange={handleChange}
            />
          }
        />
      </Grid>
      {state.options?.cache && (
        <Grid item sm={6} xs={12}>
          <Typography gutterBottom>Cache Threshold<HelpTip text="How similar a new question must be to a cached one to reuse the answer (higher = stricter match)" /></Typography>
          <Slider
            name="cache_threshold"
            value={(state.options?.cache_threshold ?? 0.85) * 100}
            onChange={handleChange}
            step={1}
            min={0}
            max={100}
            valueLabelDisplay="auto"
            style={{ width: "400px" }}
          />
        </Grid>
      )}
    </Grid>

    <Dialog open={aiOpen} onClose={() => !aiLoading && setAiOpen(false)} maxWidth="sm" fullWidth>
      <DialogTitle>Generate system prompt with AI</DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Describe in plain English what this project does. The system LLM will draft a full system prompt you can then edit.
        </Typography>
        <TextField
          autoFocus
          fullWidth
          multiline
          minRows={3}
          placeholder={'e.g. "customer support assistant for my SaaS billing product"'}
          value={aiDescription}
          onChange={(e) => setAiDescription(e.target.value)}
          disabled={aiLoading}
        />
        <Alert severity="info" sx={{ mt: 2 }}>
          This replaces the current system message. Copy the existing one first if you want to keep it.
        </Alert>
      </DialogContent>
      <DialogActions>
        <Button onClick={() => setAiOpen(false)} disabled={aiLoading}>Cancel</Button>
        <Button
          variant="contained"
          onClick={handleGeneratePrompt}
          disabled={aiLoading || !aiDescription.trim()}
          startIcon={aiLoading ? <CircularProgress size={16} /> : <AutoAwesome />}
        >
          {aiLoading ? "Generating..." : "Generate"}
        </Button>
      </DialogActions>
    </Dialog>
    </Fragment>
  );
}
