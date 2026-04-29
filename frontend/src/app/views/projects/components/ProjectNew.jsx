import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  Chip,
  Divider,
  Grid,
  ListItemText,
  MenuItem,
  styled,
  Tab,
  Tabs,
  TextField,
  Typography
} from "@mui/material";
import {
  Memory, Cloud, Lock, AttachMoney, Token, Storage, DataArray, Hub,
} from "@mui/icons-material";

import { H4 } from "app/components/Typography";
import api from "app/utils/api";
import BAvatar from "boring-avatars";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

const Form = styled("form")(() => ({ padding: "16px" }));

export default function ProjectNew({ projects, info, template }) {
  const { platformCapabilities } = usePlatformCapabilities();
  const typeList = ["agent", "rag", "block", ...(platformCapabilities?.app_builder ? ["app"] : [])];
  const typeDescriptions = {
    agent: "Direct LLM interaction for chat, completion, and multimodal tasks. Optionally attach built-in tools or MCP servers in the Tools tab to turn it into a tool-using agent. The most common project type.",
    rag: "Retrieval-Augmented Generation. Interact with your own knowledge base fed by uploaded documents.",
    block: "Visual logic builder. Chain multiple projects and implement custom logic using a graphical block-based IDE. No LLM required.",
    app: "App builder. Describe an app and the LLM scaffolds a vanilla TypeScript + PHP + SQLite project, edited in an in-browser IDE with live preview. Output is fully standalone — no RESTai dependency — and deployable via FTP/SFTP or ZIP.",
  };
  var vectorstoreList = info.vectorstores || ["chroma"];
  const auth = useAuth();
  const navigate = useNavigate();

  const [tabIndex, setTabIndex] = useState("0");
  const [state, setState] = useState({});
  const [teams, setTeams] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [teamLLMs, setTeamLLMs] = useState([]);
  const [teamEmbeddings, setTeamEmbeddings] = useState([]);

  // Fetch teams the user belongs to
  const fetchTeams = () => {
    api.get("/teams", auth.user.token)
      .then((d) => {
        setTeams(d.teams || []);
      })
      .catch(() => {});
  };

  // Fetch team details including available LLMs and embeddings
  const fetchTeamDetails = (teamId) => {
    api.get("/teams/" + teamId, auth.user.token)
      .then((team) => {
        setSelectedTeam(team);

        const availableLLMs = team.llms || [];
        const filteredLLMs = info.llms.filter(llm =>
          availableLLMs.some(teamLLM => teamLLM.name === llm.name)
        );
        setTeamLLMs(filteredLLMs);

        const availableEmbeddings = team.embeddings || [];
        const filteredEmbeddings = info.embeddings.filter(embedding =>
          availableEmbeddings.some(teamEmbedding => teamEmbedding.name === embedding.name)
        );
        setTeamEmbeddings(filteredEmbeddings);

        // Auto-select when there's only one option
        setState(prev => ({
          ...prev,
          projectllm: filteredLLMs.length === 1 ? filteredLLMs[0].name : prev.projectllm || '',
          projectembeddings: filteredEmbeddings.length === 1 ? filteredEmbeddings[0].name : prev.projectembeddings || '',
          projectvectorstore: vectorstoreList.length === 1 ? vectorstoreList[0] : prev.projectvectorstore || '',
        }));
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchTeams();
    if (template) {
      setState(prev => ({ ...prev, projecttype: template.type }));
    }
  }, []);

  const handleTeamChange = (e) => {
    const teamId = e.target.value;
    setState({ ...state, team_id: teamId, projectllm: '', projectembeddings: '' }); // Reset model selections
    if (teamId) {
      fetchTeamDetails(teamId);
    } else {
      setSelectedTeam(null);
      setTeamLLMs([]);
      setTeamEmbeddings([]);
    }
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    console.log(state);

    var opts = {
      "name": state.projectname,
      "type": state.projecttype
    }

    if (state.projecttype !== "block") {
      opts.llm = state.projectllm;
    }

    if (state.projecttype === "rag") {
      opts.embeddings = state.projectembeddings;
      opts.vectorstore = state.projectvectorstore;
    }

    if (state.team_id) {
      opts.team_id = state.team_id;
    }

    if (template && template.human_description) {
      opts.human_description = template.human_description || template.description;
    }

    api.post("/projects", opts, auth.user.token)
      .then(async (response) => {
        // Apply template settings via PATCH
        if (template && (template.system || (template.options && Object.keys(template.options).length > 0))) {
          const patchOpts = {};
          if (template.system) patchOpts.system = template.system;
          if (template.options) patchOpts.options = template.options;
          if (template.description) patchOpts.human_description = template.description;
          try {
            await api.patch("/projects/" + response.project, patchOpts, auth.user.token);
          } catch (e) {
            // Template settings failed — project is created, user can fix in edit
          }
        }
        // App-builder projects land on the builder, not the generic info page.
        if (state.projecttype === "app") {
          navigate("/project/" + response.project + "/builder");
        } else {
          navigate("/project/" + response.project);
        }
      }).catch(() => {});
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  return (
    <Card elevation={3}>
      <H4 p={2}>{template ? `New Project: ${template.name}` : "Add a New Project"}</H4>

      <Divider sx={{ mb: 1 }} />

      {template && (
        <Alert severity="info" sx={{ mx: 2, mt: 1 }}>
          <strong>{template.name}</strong> — {template.description}
          {template.system && (
            <Typography variant="caption" display="block" sx={{ mt: 0.5, fontStyle: "italic" }}>
              System prompt and settings will be applied automatically after creation.
            </Typography>
          )}
        </Alert>
      )}

      <Grid container spacing={2}>

        <Grid item xs={6}>
          <H4 p={2}>Project Info</H4>
          <Form onSubmit={handleSubmit}>
            <Grid item md={2} sm={4} xs={12} sx={{ mb: 2 }}>
              <BAvatar name={state.projectname || "Default"} size={84} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]}/>
            </Grid>
            <Grid container spacing={3} alignItems="center">
              <Grid item md={2} sm={4} xs={12}>
                Name
              </Grid>

              <Grid item md={10} sm={8} xs={12}>
                <TextField
                  size="small"
                  name="projectname"
                  variant="outlined"
                  label="Project Name"
                  fullWidth
                  onChange={handleChange}
                />
              </Grid>

              <Grid item md={2} sm={4} xs={12}>
                Team
              </Grid>

              <Grid item md={10} sm={8} xs={12}>
                <TextField
                  select
                  size="small"
                  name="team_id"
                  label="Team"
                  variant="outlined"
                  value={state.team_id ?? ''}
                  onChange={handleTeamChange}
                  fullWidth
                  required
                  helperText="A project can only belong to one team"
                >
                  {teams.map((team) => (
                    <MenuItem value={team.id} key={team.id}>
                      {team.name}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>

              {selectedTeam && (
                <>
                  <Grid item md={2} sm={4} xs={12}>
                    Type
                  </Grid>

                  <Grid item md={10} sm={8} xs={12}>
                    <TextField
                      select
                      size="small"
                      name="projecttype"
                      label="Type"
                      variant="outlined"
                      onChange={handleChange}
                      fullWidth
                      disabled={!!template}
                      value={state.projecttype || ""}
                      helperText={state.projecttype ? typeDescriptions[state.projecttype] : "Select the project type"}
                    >
                      {typeList.map((item) => (
                        <MenuItem value={item} key={item}>
                          <ListItemText
                            primary={item}
                            secondary={typeDescriptions[item]}
                          />
                        </MenuItem>
                      ))}
                    </TextField>
                  </Grid>
                </>
              )}

              {selectedTeam && state.projecttype && state.projecttype !== "block" && (
                <>
                  <Grid item md={2} sm={4} xs={12}>
                    LLM
                  </Grid>

                  <Grid item md={10} sm={8} xs={12}>
                    <TextField
                      select
                      size="small"
                      name="projectllm"
                      label="LLM"
                      variant="outlined"
                      value={state.projectllm || ""}
                      onChange={handleChange}
                      fullWidth
                      helperText={teamLLMs.length === 0 ? "No LLMs available for this team" : ""}
                    >
                      {teamLLMs
                        .map((item) => (
                          <MenuItem value={item.name} key={item.name}>
                            {item.name}
                          </MenuItem>
                        ))
                      }
                    </TextField>
                  </Grid>
                </>
              )}
            </Grid>

            <Tabs
              value={tabIndex}
              textColor="primary"
              indicatorColor="primary"
              sx={{ mt: 0, mb: 0 }}>

              {state.projecttype === "rag" && (
                <Tab key="0" value="0" label="RAG" sx={{ textTransform: "capitalize" }} />
              )}
            </Tabs>

            {selectedTeam && state.projecttype === "rag" && tabIndex === "0" && (
              <Grid container spacing={3} alignItems="center">
                <Grid item md={2} sm={4} xs={12}>
                  Embeddings
                </Grid>

                <Grid item md={10} sm={8} xs={12}>
                  <TextField
                    select
                    size="small"
                    name="projectembeddings"
                    label="Embeddings"
                    variant="outlined"
                    value={state.projectembeddings || ""}
                    fullWidth
                    onChange={handleChange}
                    helperText={teamEmbeddings.length === 0 ? "No embeddings available for this team" : ""}
                  >
                    {teamEmbeddings.map((item) => (
                      <MenuItem value={item.name} key={item.name}>
                        {item.name}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>

                <Grid item md={2} sm={4} xs={12}>
                  Vectorstore
                </Grid>

                <Grid item md={10} sm={8} xs={12}>
                  <TextField
                    select
                    size="small"
                    name="projectvectorstore"
                    label="Vectorstore"
                    variant="outlined"
                    value={state.projectvectorstore || ""}
                    fullWidth
                    onChange={handleChange}
                  >
                    {vectorstoreList.map((item) => (
                      <MenuItem value={item} key={item}>
                        {item}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
              </Grid>
            )}

            <Box mt={3}>
              <Button color="primary" variant="contained" type="submit">
                Submit
              </Button>
            </Box>
          </Form>
        </Grid>
        <Grid item xs={6}>
          <Box sx={{ p: 2, display: "flex", flexDirection: "column", gap: 2 }}>
            {(() => {
              const llm = state.projectllm ? teamLLMs.find(l => l.name === state.projectllm) : null;
              const emb = state.projectembeddings ? teamEmbeddings.find(e => e.name === state.projectembeddings) : null;
              const vs = state.projectvectorstore;
              const hasSelection = llm || emb || vs || state.projecttype;

              if (!hasSelection) return (
                <Box sx={{ textAlign: "center", py: 6, color: "text.disabled" }}>
                  <Memory sx={{ fontSize: 48, mb: 1, opacity: 0.3 }} />
                  <Typography variant="body2">Select options to see details</Typography>
                </Box>
              );

              return (
                <>
                  {/* Project type summary */}
                  {state.projecttype && (
                    <Box sx={{ p: 2, borderRadius: 2, bgcolor: "action.hover" }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                        <Hub sx={{ fontSize: 20, color: "primary.main" }} />
                        <Typography variant="subtitle2">Project Type</Typography>
                      </Box>
                      <Chip label={state.projecttype.toUpperCase()} size="small" color="primary" variant="outlined" />
                      <Typography variant="caption" display="block" sx={{ mt: 0.5, color: "text.secondary" }}>
                        {typeDescriptions[state.projecttype]}
                      </Typography>
                    </Box>
                  )}

                  {/* LLM card */}
                  {llm && (
                    <Box sx={{ p: 2, borderRadius: 2, border: "1px solid", borderColor: "divider" }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                        <Memory sx={{ fontSize: 20, color: "success.main" }} />
                        <Typography variant="subtitle2">LLM</Typography>
                      </Box>
                      <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>{llm.name}</Typography>
                      {llm.description && (
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{llm.description}</Typography>
                      )}
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                        <Chip icon={<Cloud sx={{ fontSize: 16 }} />} label={llm.class_name} size="small" variant="outlined" />
                        <Chip
                          icon={<Lock sx={{ fontSize: 16 }} />}
                          label={llm.privacy}
                          size="small"
                          color={llm.privacy === "private" ? "success" : "default"}
                          variant="outlined"
                        />
                        {llm.context_window && (
                          <Chip icon={<Token sx={{ fontSize: 16 }} />} label={`${(llm.context_window / 1000).toFixed(0)}K context`} size="small" variant="outlined" />
                        )}
                      </Box>
                      {(llm.input_cost > 0 || llm.output_cost > 0) && (
                        <Box sx={{ display: "flex", gap: 2, mt: 1.5 }}>
                          <Box>
                            <Typography variant="caption" color="text.secondary">Input cost</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              <AttachMoney sx={{ fontSize: 14, verticalAlign: "middle" }} />{llm.input_cost}/1K tokens
                            </Typography>
                          </Box>
                          <Box>
                            <Typography variant="caption" color="text.secondary">Output cost</Typography>
                            <Typography variant="body2" sx={{ fontWeight: 600 }}>
                              <AttachMoney sx={{ fontSize: 14, verticalAlign: "middle" }} />{llm.output_cost}/1K tokens
                            </Typography>
                          </Box>
                        </Box>
                      )}
                    </Box>
                  )}

                  {/* Embeddings card */}
                  {emb && (
                    <Box sx={{ p: 2, borderRadius: 2, border: "1px solid", borderColor: "divider" }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
                        <DataArray sx={{ fontSize: 20, color: "info.main" }} />
                        <Typography variant="subtitle2">Embeddings</Typography>
                      </Box>
                      <Typography variant="h6" sx={{ fontWeight: 700, mb: 0.5 }}>{emb.name}</Typography>
                      {emb.description && (
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>{emb.description}</Typography>
                      )}
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1 }}>
                        <Chip icon={<Cloud sx={{ fontSize: 16 }} />} label={emb.class_name} size="small" variant="outlined" />
                        <Chip
                          icon={<Lock sx={{ fontSize: 16 }} />}
                          label={emb.privacy}
                          size="small"
                          color={emb.privacy === "private" ? "success" : "default"}
                          variant="outlined"
                        />
                        {emb.dimension && (
                          <Chip label={`${emb.dimension}d`} size="small" variant="outlined" />
                        )}
                      </Box>
                    </Box>
                  )}

                  {/* Vectorstore card */}
                  {vs && (
                    <Box sx={{ p: 2, borderRadius: 2, border: "1px solid", borderColor: "divider" }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                        <Storage sx={{ fontSize: 20, color: "warning.main" }} />
                        <Typography variant="subtitle2">Vector Store</Typography>
                      </Box>
                      <Chip label={vs} size="small" color="warning" variant="outlined" />
                    </Box>
                  )}
                </>
              );
            })()}
          </Box>
        </Grid>
      </Grid>
    </Card>
  );
}
