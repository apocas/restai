import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  Divider,
  Grid,
  MenuItem,
  styled,
  Tab,
  Tabs,
  TextField
} from "@mui/material";

import { H4 } from "app/components/Typography";
import { toast } from 'react-toastify';
import ReactJson from '@microlink/react-json-view';
import BAvatar from "boring-avatars";

const Form = styled("form")(() => ({ padding: "16px" }));

export default function ProjectNew({ projects, info }) {
  const typeList = ["rag", "inference", "agent", "ragsql", "vision", "router"];
  var vectorstoreList = ["redis", "chroma"];
  const auth = useAuth();
  const navigate = useNavigate();

  if (process.env.REACT_APP_RESTAI_VECTOR) {
    vectorstoreList = process.env.REACT_APP_RESTAI_VECTOR.split(",")
  }

  const [tabIndex, setTabIndex] = useState("0");
  const [state, setState] = useState({});
  const [teams, setTeams] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [teamLLMs, setTeamLLMs] = useState([]);
  const [teamEmbeddings, setTeamEmbeddings] = useState([]);

  const url = process.env.REACT_APP_RESTAI_API_URL || "";

  // Fetch teams the user belongs to
  const fetchTeams = () => {
    fetch(url + "/teams", { 
      headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token })
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((d) => {
        setTeams(d.teams || []);
      })
      .catch(err => {
        console.log("Error fetching teams:", err.toString());
      });
  };

  // Fetch team details including available LLMs and embeddings
  const fetchTeamDetails = (teamId) => {
    fetch(url + "/teams/" + teamId, { 
      headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token })
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
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
      .catch(err => {
        console.log("Error fetching team details:", err.toString());
        toast.error("Failed to load team models");
      });
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
      "llm": state.projectllm,
      "type": state.projecttype
    }

    if (state.projecttype === "rag") {
      opts.embeddings = state.projectembeddings;
      opts.vectorstore = state.projectvectorstore;
    }

    if (state.team_id) {
      opts.team_id = state.team_id;
    }

    fetch(url + "/projects", {
      method: 'POST',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      body: JSON.stringify(opts),
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((response) => {
        navigate("/project/" + response.project);
      }).catch(err => {
        toast.error(err.toString());
      });
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
                    >
                      {typeList.map((item) => (
                        <MenuItem value={item} key={item}>
                          {item}
                        </MenuItem>
                      ))}
                    </TextField>
                  </Grid>
                </>
              )}

              {selectedTeam && state.projecttype && (
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
                        .filter(item =>
                          state.projecttype === "vision"
                            ? item.type === "vision"
                            : item.type !== "vision"
                        )
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
