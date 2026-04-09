import { Card, Divider, Box, Grid, TextField, Button, Typography, MenuItem, CircularProgress, Chip } from "@mui/material";
import { H4 } from "app/components/Typography";
import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { JsonEditor } from 'json-edit-react';
import { PROVIDER_CONFIG } from '../providerConfig';
import api from "app/utils/api";

const OPENAI_COMPAT_CLASSES = new Set([
  "OpenAI", "OpenAILike", "LiteLLM", "vLLM", "Groq", "Grok", "Gemini", "GeminiMultiModal",
]);

export default function LLMEdit({ llm }) {
  const auth = useAuth();
  const [state, setState] = useState({});
  const [remoteModels, setRemoteModels] = useState(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = (event) => {
    event.preventDefault();

    var update = {};

    if (state.name !== llm.name) {
      update.name = state.name;
    }
    if (state.class_name !== llm.class_name) {
      update.class_name = state.class_name;
    }
    if (state.options !== llm.options) {
      update.options = state.options;
    }
    if (state.privacy !== llm.privacy) {
      update.privacy = state.privacy;
    }
    if (state.description !== llm.description) {
      update.description = state.description;
    }
    if (state.input_cost !== llm.input_cost) {
      update.input_cost = state.input_cost;
    }
    if (state.output_cost !== llm.output_cost) {
      update.output_cost = state.output_cost;
    }
    if (state.context_window !== llm.context_window) {
      update.context_window = parseInt(state.context_window);
    }

    api.patch("/llms/" + llm.id, update, auth.user.token)
      .then(() => {
        window.location.href = "/admin/llm/" + llm.id;
      }).catch(() => {});
  }

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  const handleListModels = async () => {
    setLoadingModels(true);
    setRemoteModels(null);
    try {
      const opts = state.options || {};
      const result = await api.post("/tools/openai-compat/models", {
        api_base: opts.api_base || opts.base_url || "",
        api_key: opts.api_key || "",
      }, auth.user.token);
      setRemoteModels(result.models || []);
    } catch (err) {
      setRemoteModels([]);
    } finally {
      setLoadingModels(false);
    }
  };

  const handleSelectModel = (modelId) => {
    setState({
      ...state,
      options: { ...state.options, model: modelId },
    });
    setRemoteModels(null);
  };

  const canListModels = OPENAI_COMPAT_CLASSES.has(state.class_name);

  useEffect(() => {
    setState(llm);
  }, [llm]);

  return (
    <Card elevation={3}>
      <H4 p={2}>Edit LLM - {llm.name}</H4>

      <Divider sx={{ mb: 1 }} />

      <form onSubmit={handleSubmit}>
        <Box margin={3}>
          <Grid container spacing={3}>
            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="name"
                label="Name"
                variant="outlined"
                onChange={handleChange}
                value={state.name}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                select
                InputLabelProps={{ shrink: true }}
                name="class_name"
                label="Class Name"
                variant="outlined"
                onChange={handleChange}
                value={state.class_name || ""}
              >
                {Object.entries(PROVIDER_CONFIG).map(([key, config]) => (
                  <MenuItem key={key} value={key}>{config.label}</MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid item sm={6} xs={12}>
              <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 1 }}>
                <Typography variant="h6">Options</Typography>
                {canListModels && (
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={handleListModels}
                    disabled={loadingModels}
                    startIcon={loadingModels ? <CircularProgress size={16} /> : null}
                  >
                    {loadingModels ? "Loading..." : "List Models"}
                  </Button>
                )}
              </Box>

              {remoteModels && remoteModels.length > 0 && (
                <Box sx={{
                  mb: 2, p: 1.5, borderRadius: 1,
                  border: "1px solid", borderColor: "divider",
                  maxHeight: 200, overflowY: "auto",
                }}>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                    {remoteModels.length} model{remoteModels.length !== 1 ? "s" : ""} available — click to select
                  </Typography>
                  <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                    {remoteModels.map((m) => (
                      <Chip
                        key={m.id}
                        label={m.id}
                        size="small"
                        variant={state.options?.model === m.id ? "filled" : "outlined"}
                        color={state.options?.model === m.id ? "primary" : "default"}
                        onClick={() => handleSelectModel(m.id)}
                        sx={{ cursor: "pointer" }}
                      />
                    ))}
                  </Box>
                </Box>
              )}

              {remoteModels && remoteModels.length === 0 && !loadingModels && (
                <Typography variant="body2" color="error" sx={{ mb: 2 }}>
                  No models found. Check the API base URL and API key in the options below.
                </Typography>
              )}

              <JsonEditor
                data={state.options || {}}
                setData={(updatedOptions) => setState({ ...state, options: updatedOptions })}
                restrictDelete={false}
                rootName="Options"
                numberType="float"
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                select
                InputLabelProps={{ shrink: true }}
                name="privacy"
                label="Privacy"
                variant="outlined"
                onChange={handleChange}
                value={state.privacy || ""}
              >
                {["public", "private"].map((p) => (
                  <MenuItem key={p} value={p}>{p}</MenuItem>
                ))}
              </TextField>
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="description"
                label="Description"
                variant="outlined"
                onChange={handleChange}
                value={state.description}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="input_cost"
                label="Input Cost"
                variant="outlined"
                onChange={handleChange}
                value={state.input_cost}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="output_cost"
                label="Output Cost"
                variant="outlined"
                onChange={handleChange}
                value={state.output_cost}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="context_window"
                label="Context Window"
                type="number"
                variant="outlined"
                onChange={handleChange}
                value={state.context_window}
                helperText="Maximum number of tokens the LLM can process"
              />
            </Grid>

            <Grid item xs={12}>
              <Button type="submit" variant="contained">
                Save Changes
              </Button>
              <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/llms") }}>
                Cancel
              </Button>
            </Grid>
          </Grid>
        </Box>
      </form>
    </Card>
  );
}
