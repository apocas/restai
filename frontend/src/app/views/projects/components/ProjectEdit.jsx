import { Card, Divider, Box, Grid, TextField, Button, MenuItem, Switch, Autocomplete, Slider, Typography, IconButton, CircularProgress } from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import FormControlLabel from "@mui/material/FormControlLabel";
import { H4 } from "app/components/Typography";
import { useState, useEffect, Fragment } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { JsonEditor } from 'json-edit-react';
import api from "app/utils/api";

export default function ProjectEdit({ project, projects, info }) {
  const auth = useAuth();
  const [state, setState] = useState({});
  const [tools, setTools] = useState([]);
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [mcpServers, setMcpServers] = useState([]);
  const [promptVersions, setPromptVersions] = useState([]);
  const [showVersions, setShowVersions] = useState(false);
  const navigate = useNavigate();

  const handleAddMcpServer = () => {
    setMcpServers([...mcpServers, { host: "", args: [], env: {}, tools: null, availableTools: [], loading: false, error: null }]);
  };

  const handleRemoveMcpServer = (index) => {
    setMcpServers(mcpServers.filter((_, i) => i !== index));
  };

  const handleMcpServerFieldChange = (index, field, value) => {
    const updated = [...mcpServers];
    updated[index] = { ...updated[index], [field]: value };
    setMcpServers(updated);
  };

  const handleProbeMcpServer = (index) => {
    const server = mcpServers[index];
    const updated = [...mcpServers];
    updated[index] = { ...updated[index], loading: true, error: null };
    setMcpServers(updated);

    const body = { host: server.host };
    if (server.args && server.args.length > 0) body.args = server.args;
    if (server.env && Object.keys(server.env).length > 0) body.env = server.env;

    api.post("/tools/mcp/probe", body, auth.user.token)
      .then((data) => {
        setMcpServers(prev => {
          const next = [...prev];
          next[index] = { ...next[index], availableTools: data.tools || [], loading: false, error: null };
          return next;
        });
      })
      .catch((err) => {
        setMcpServers(prev => {
          const next = [...prev];
          next[index] = { ...next[index], loading: false, error: err.message };
          return next;
        });
      });
  };

  const handleMcpToolsChange = (index, selectedToolNames) => {
    const updated = [...mcpServers];
    updated[index] = { ...updated[index], tools: selectedToolNames.length > 0 ? selectedToolNames.join(",") : null };
    setMcpServers(updated);
  };

  const isStdioServer = (host) => {
    return host && !host.startsWith("http://") && !host.startsWith("https://");
  };

  const handleSubmit = (event) => {
    event.preventDefault();

    var opts = {
      "name": project.name,
      "llm": state.llm,
      "human_description": state.human_description,
      "human_name": state.human_name,
      "guard": state.guard || "",
      "censorship": state.censorship || "",
      "public": state.public,
      "default_prompt": state.default_prompt || "",
      "options": state.options || {}
    }

    // Make sure we preserve the logging option if it exists in the state
    if (state.options.logging !== undefined) {
      opts.options.logging = state.options.logging;
    }

    if (state.team && state.team.id) {
      opts.team_id = state.team.id;
    }

    if (state.selectedUsers && state.selectedUsers.length > 0) {
      opts.users = state.selectedUsers.map(user => user.username);
    }

    if (project.type === "rag" || project.type === "inference" || project.type === "agent") {
      opts.system = state.system
    }

    if (project.type === "agent") {
      opts.options.tools = state.options.tools

      const filteredMcpServers = mcpServers
        .filter(s => s.host.trim() !== "")
        .map(s => {
          const entry = { host: s.host, tools: s.tools || null };
          if (s.args && s.args.length > 0) entry.args = s.args;
          if (s.env && Object.keys(s.env).length > 0) entry.env = s.env;
          return entry;
        });
      opts.options.mcp_servers = filteredMcpServers.length > 0 ? filteredMcpServers : null;
    }

    if (state.options.telegram_token !== undefined) {
      opts.options.telegram_token = state.options.telegram_token;
    }

    opts.options.rate_limit = state.options.rate_limit ? parseInt(state.options.rate_limit) : null;
    opts.options.guard_output = state.options.guard_output || null;
    opts.options.guard_mode = state.options.guard_mode || "block";
    opts.options.fallback_llm = state.options.fallback_llm || null;
    opts.options.cache = state.options.cache
    opts.options.cache_threshold = parseFloat(state.options.cache_threshold) || 0.85

    if (project.type === "rag") {
      opts.options.colbert_rerank = state.options.colbert_rerank
      opts.options.llm_rerank = state.options.llm_rerank
      opts.options.score = parseFloat(state.options.score) || 0.0
      opts.options.k = parseInt(state.options.k) || 4
      opts.options.connection = state.options.connection || null
      opts.options.tables = state.options.tables || null

      if (opts.censorship.trim() === "") {
        delete opts.options.censorship;
      }
    }

    api.patch("/projects/" + project.id, opts, auth.user.token)
      .then(() => {
        navigate("/project/" + project.id);
      }).catch(() => {});
  }

  const fetchTools = () => {
    return api.get("/tools/agent", auth.user.token)
      .then((d) => {
        setTools(d)
      }).catch(() => {});
  }

  const fetchUsers = () => {
    return api.get("/users", auth.user.token)
      .then((d) => {
        setUsers(d.users);
      }).catch(() => {});
  }

  const fetchTeams = () => {
    return api.get("/teams", auth.user.token)
      .then((d) => {
        setTeams(d.teams || []);
      })
      .catch(() => {});
  };

  // Add a specific handler for team selection that fetches team details
  const handleTeamChange = (event) => {
    const teamId = event.target.value;

    // First update the team_id in state
    setState(prevState => ({
      ...prevState,
      team_id: teamId
    }));

    // Then fetch the complete team details to get LLMs and embeddings
    if (teamId) {
      api.get("/teams/" + teamId, auth.user.token)
        .then((teamData) => {
          // Update state with the full team object
          setState(prevState => ({
            ...prevState,
            team: teamData
          }));
        })
        .catch(() => {});
    } else {
      // If no team is selected, clear the team object
      setState(prevState => ({
        ...prevState,
        team: null
      }));
    }
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();

    // Handle options properties
    if (["logging", "cache", "llm_rerank", "colbert_rerank"].includes(event.target.name)) {
      setState({
        ...state,
        options: {
          ...state.options,
          [event.target.name]: event.target.checked
        }
      });
    } 
    // Handle slider changes for cache_threshold
    else if (event.target.name === "cache_threshold") {
      setState({ 
        ...state, 
        options: {
          ...state.options,
          cache_threshold: event.target.value / 100
        }
      });
    }
    // Handle K field (slider)
    else if (event.target.name === "k") {
      setState({ 
        ...state, 
        options: {
          ...state.options,
          k: parseInt(event.target.value)
        }
      });
    }
    // Handle score field (text input - store as string during editing)
    else if (event.target.name === "score") {
      setState({ 
        ...state, 
        options: {
          ...state.options,
          score: event.target.value
        }
      });
    }
    else if (event.target.name === "telegram_token") {
      setState({ ...state, options: { ...state.options, telegram_token: event.target.value } });
    }
    else if (event.target.name === "connection" || event.target.name === "tables") {
      setState({ ...state, options: { ...state.options, [event.target.name]: event.target.value } });
    }
    else if (event.target.name === "rate_limit") {
      setState({ ...state, options: { ...state.options, rate_limit: event.target.value ? parseInt(event.target.value) : null } });
    }
    else {
      setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
    }
  };

  useEffect(() => {
    // Initialize state with project data, ensuring options object exists
    const initialState = {
      ...project,
      options: {
        logging: false,
        colbert_rerank: false,
        llm_rerank: false,
        cache: false,
        cache_threshold: 0.85,
        score: 0.0,
        k: 4,
        tools: null,
        ...project.options
      }
    };
    
    setState(initialState);
    fetchTools();
    fetchUsers();
    fetchTeams();

    // Fetch prompt versions
    if (project.id && project.type !== "block") {
      api.get("/projects/" + project.id + "/prompts", auth.user.token, { silent: true })
        .then((versions) => setPromptVersions(versions || []))
        .catch(() => {});
    }

    // Initialize MCP servers from project options
    if (project.type === "agent" && project.options?.mcp_servers) {
      const servers = project.options.mcp_servers.map(s => ({
        host: s.host,
        args: s.args || [],
        env: s.env || {},
        tools: s.tools || null,
        availableTools: s.tools ? s.tools.split(",").map(t => ({ name: t.trim(), description: "", schema: "" })) : [],
        loading: false,
        error: null,
      }));
      setMcpServers(servers);

      // Auto-probe each server to get available tools
      servers.forEach((server, index) => {
        if (server.host) {
          const body = { host: server.host };
          if (server.args && server.args.length > 0) body.args = server.args;
          if (server.env && Object.keys(server.env).length > 0) body.env = server.env;

          api.post("/tools/mcp/probe", body, auth.user.token, { silent: true })
            .then(data => {
              setMcpServers(prev => {
                const next = [...prev];
                next[index] = { ...next[index], availableTools: data.tools || [] };
                return next;
              });
            })
            .catch(() => { /* silently fail on auto-probe */ });
        }
      });
    }

    // If the project has a team, fetch its complete details
    if (project && project.team && project.team.id) {
      api.get("/teams/" + project.team.id, auth.user.token, { silent: true })
        .then(teamData => {
          // Update state with full team details, preserving other state properties
          setState(prevState => ({
            ...prevState,
            team: teamData
          }));
        })
        .catch(() => {});
    }
  }, [project, auth.user.token]);

  useEffect(() => {
    if (project && project.users) {
      const projectUsers = users.filter(user =>
        project.users.includes(user.username)
      );
      setState(prev => ({
        ...prev,
        selectedUsers: projectUsers
      }));
    }
  }, [users, project]);

  return (
    <Card elevation={3}>
      <H4 p={2}>Edit project - {project.name}</H4>

      <Divider sx={{ mb: 1 }} />

      <form onSubmit={handleSubmit}>
        <Box margin={3}>
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
                  label="Shared"
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
                label="Logging"
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
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="rate_limit"
                label="Rate Limit (requests/min)"
                variant="outlined"
                type="number"
                onChange={handleChange}
                value={state.options?.rate_limit ?? ''}
                helperText="Maximum requests per minute. Leave empty for unlimited."
                inputProps={{ min: 1, max: 10000 }}
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
                  {/* Only show LLMs the project's team has access to */}
                  {info.llms
                    .filter(item => {
                      // If no team is selected, show LLMs based on project type only
                      if (!state.team) return true;

                      // Get team LLMs - convert to array of names if they're objects
                      const teamLLMs = state.team.llms || [];
                      const teamLLMNames = teamLLMs.map(llm => typeof llm === 'string' ? llm : llm.name);

                      // Filter by both team access and project type
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

            {state.type !== "block" && (
              <Grid item sm={6} xs={12}>
                <TextField
                  fullWidth
                  select
                  label="Fallback LLM"
                  variant="outlined"
                  value={state.options?.fallback_llm ?? ''}
                  onChange={(e) => setState({ ...state, options: { ...state.options, fallback_llm: e.target.value || null } })}
                  helperText="Used automatically if the primary LLM fails"
                >
                  <MenuItem value="">None</MenuItem>
                  {info.llms
                    .filter(item => {
                      if (!state.team) return true;
                      const teamLLMs = state.team.llms || [];
                      const teamLLMNames = teamLLMs.map(llm => typeof llm === 'string' ? llm : llm.name);
                      return teamLLMNames.includes(item.name);
                    })
                    .filter(item => item.name !== state.llm)
                    .map((item) => (
                      <MenuItem value={item.name} key={item.name}>
                        {item.name}
                      </MenuItem>
                    ))}
                </TextField>
              </Grid>
            )}

            {(state.type === "rag" || state.type === "inference" || state.type === "agent") && state.type !== "block" && (
              <Fragment>
                <Grid item sm={12} xs={12}>
                  <Divider sx={{ mb: 1 }} />
                </Grid>
                <Grid item sm={12} xs={12}>
                  <Typography variant="subtitle1" gutterBottom>System Message</Typography>
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
                        {showVersions ? " ▲" : " ▼"}
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
              <Autocomplete
                options={projects.filter((p) => p.name !== project.name).map((p) => p.name)}
                value={state.guard || null}
                onChange={(event, newValue) => {
                  setState({ ...state, guard: newValue || "" });
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    label="Input Guard"
                    variant="outlined"
                    helperText="Project that evaluates user input before inference"
                  />
                )}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <Autocomplete
                options={projects.filter((p) => p.name !== project.name).map((p) => p.name)}
                value={state.options?.guard_output || null}
                onChange={(event, newValue) => {
                  setState({ ...state, options: { ...state.options, guard_output: newValue || null } });
                }}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    label="Output Guard"
                    variant="outlined"
                    helperText="Project that evaluates LLM responses after inference"
                  />
                )}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="censorship"
                label="Censorship Message"
                variant="outlined"
                onChange={handleChange}
                value={state.censorship ?? ''}
                helperText="Message returned when a guard blocks a request"
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                select
                fullWidth
                InputLabelProps={{ shrink: true }}
                label="Guard Mode"
                variant="outlined"
                value={state.options?.guard_mode || "block"}
                onChange={(e) => setState({ ...state, options: { ...state.options, guard_mode: e.target.value } })}
                helperText="Block stops the response, Warn flags but passes through"
              >
                <MenuItem value="block">Block</MenuItem>
                <MenuItem value="warn">Warn</MenuItem>
              </TextField>
            </Grid>

            {state.type === "rag" && (
              <div>
                <Grid item sm={12} xs={12}>
                  <Divider sx={{ mb: 1 }} />
                </Grid>
              </div>
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

            {state.type === "rag" && (
              <Fragment>
                <Grid item sm={12} xs={12}>
                  <Divider sx={{ mb: 1 }} />
                </Grid>
                <Grid item sm={6} xs={12}>
                  <Typography id="discrete-slider" gutterBottom>
                    K Value
                  </Typography>
                  <Slider
                    name="k"
                    value={state.options?.k ?? 4}
                    onChange={handleChange}
                    aria-labelledby="input-slider"
                    step={1}
                    min={0}
                    max={10}
                    valueLabelDisplay="auto"
                    style={{ width: "400px" }}
                  />
                </Grid>
                <Grid item sm={6} xs={12}>
                  <TextField
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    name="score"
                    label="Cutoff Score"
                    variant="outlined"
                    onChange={handleChange}
                    value={state.options?.score ?? ''}
                  />
                </Grid>
                <Grid item sm={6} xs={12}>
                  <FormControlLabel
                    label="LLM Rerank"
                    control={
                      <Switch
                        checked={state.options?.llm_rerank ?? false}
                        name="llm_rerank"
                        inputProps={{ "aria-label": "llm rerank checkbox" }}
                        onChange={handleChange}
                      />
                    }
                  />
                </Grid>
                <Grid item sm={6} xs={12}>
                  <FormControlLabel
                    label="Colbert Rerank"
                    control={
                      <Switch
                        checked={state.options?.colbert_rerank ?? false}
                        name="colbert_rerank"
                        inputProps={{ "aria-label": "colbert rerank checkbox" }}
                        onChange={handleChange}
                      />
                    }
                  />
                </Grid>
                <Grid item sm={12} xs={12}>
                  <Divider sx={{ mb: 1 }} />
                </Grid>
                <Grid item sm={12} xs={12}>
                  <Typography variant="subtitle1" gutterBottom>Natural Language to SQL</Typography>
                  <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 1 }}>
                    Connect a database to translate natural language questions into SQL queries automatically.
                  </Typography>
                </Grid>
                <Grid item sm={6} xs={12}>
                  <TextField
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    name="connection"
                    label="Database Connection String"
                    variant="outlined"
                    onChange={handleChange}
                    value={state.options?.connection ?? ''}
                    placeholder="mysql://user:pass@host/db or postgresql://user:pass@host/db"
                    helperText="MySQL or PostgreSQL connection string"
                  />
                </Grid>
                <Grid item sm={6} xs={12}>
                  <TextField
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    name="tables"
                    label="Allowed Tables"
                    variant="outlined"
                    onChange={handleChange}
                    value={state.options?.tables ?? ''}
                    placeholder="users, orders, products"
                    helperText="Comma-separated list of tables to allow (leave empty for all)"
                  />
                </Grid>
              </Fragment>
            )}

            <Fragment>
              <Grid item sm={12} xs={12}>
                <Divider sx={{ mb: 1 }} />
              </Grid>
              <Grid item sm={6} xs={12}>
                <FormControlLabel
                  label="Cache"
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
                  <Typography id="discrete-slider" gutterBottom>
                    Cache Threshold
                  </Typography>
                  <Slider
                    name="cache_threshold"
                    value={(state.options?.cache_threshold ?? 0.85) * 100}
                    onChange={handleChange}
                    aria-labelledby="input-slider"
                    step={1}
                    min={0}
                    max={100}
                    valueLabelDisplay="auto"
                    style={{ width: "400px" }}
                  />
                </Grid>
              )}
            </Fragment>

            {(state.type === "rag" || state.type === "inference" || state.type === "agent") && (
              <Fragment>
                <Grid item sm={12} xs={12}>
                  <Divider sx={{ mb: 1 }} />
                </Grid>
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
              </Fragment>
            )}

            <Grid item sm={12} xs={12}>
              <Divider sx={{ mb: 1 }} />
            </Grid>

            <Grid item sm={12} xs={12}>
              <Typography variant="h6">Options</Typography>
              <JsonEditor
                data={state.options || {}}
                setData={(updatedOptions) => setState({ ...state, options: updatedOptions })}
                restrictDelete={false}
                rootName="Options"
              />
            </Grid>

            <Grid item xs={12}>
              <Button type="submit" variant="contained">
                Save Changes
              </Button>
              <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/project/" + project.id) }}>
                Cancel
              </Button>
            </Grid>
          </Grid>
        </Box>
      </form>
    </Card>
  );
}
