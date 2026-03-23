import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
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

import { H4 } from "app/components/Typography";
import ReactJson from '@microlink/react-json-view';
import api from "app/utils/api";
import BAvatar from "boring-avatars";

const Form = styled("form")(() => ({ padding: "16px" }));

export default function ProjectNew({ projects, info }) {
  const typeList = ["inference", "rag", "agent", "block"];
  const typeDescriptions = {
    inference: "Direct LLM interaction for chat, completion, and multimodal tasks. The most common project type.",
    rag: "Retrieval-Augmented Generation. Interact with your own knowledge base fed by uploaded documents.",
    agent: "LLM agent with access to tools (MCP servers or built-in) for autonomous task execution.",
    block: "Visual logic builder. Chain multiple projects and implement custom logic using a graphical block-based IDE. No LLM required.",
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

        // Get the team's available LLMs from the team response
        const availableLLMs = team.llms || [];
        // Map LLM ids/names to full LLM objects by matching with info.llms
        const filteredLLMs = info.llms.filter(llm =>
          availableLLMs.some(teamLLM => teamLLM.name === llm.name)
        );
        setTeamLLMs(filteredLLMs);

        // Get the team's available embeddings from the team response
        const availableEmbeddings = team.embeddings || [];
        // Map embedding ids/names to full embedding objects by matching with info.embeddings
        const filteredEmbeddings = info.embeddings.filter(embedding =>
          availableEmbeddings.some(teamEmbedding => teamEmbedding.name === embedding.name)
        );
        setTeamEmbeddings(filteredEmbeddings);
      })
      .catch(() => {});
  };

  useEffect(() => {
    fetchTeams();
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

    api.post("/projects", opts, auth.user.token)
      .then((response) => {
        navigate("/project/" + response.project);
      }).catch(() => {});
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  return (
    <Card elevation={3}>
      <H4 p={2}>Add a New Project</H4>

      <Divider sx={{ mb: 1 }} />

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
          {state.projectllm && (
            <>
              <H4 p={2}>LLM Model</H4>
              <ReactJson src={teamLLMs.find(llm => llm.name === state.projectllm)} enableClipboard={false} name={false} />
            </>
          )}
          {state.projectembeddings && (
            <>
              <H4 p={2}>Embeddings Model</H4>
              <ReactJson src={teamEmbeddings.find(embedding => embedding.name === state.projectembeddings)} enableClipboard={false} name={false} />
            </>
          )}
        </Grid>
      </Grid>
    </Card>
  );
}
