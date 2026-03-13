import { Card, Divider, Box, Grid, TextField, Button, MenuItem, Switch, Autocomplete, Slider, Typography } from "@mui/material";
import FormControlLabel from "@mui/material/FormControlLabel";
import { H4 } from "app/components/Typography";
import { useState, useEffect, Fragment } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { toast } from 'react-toastify';
import { JsonEditor } from 'json-edit-react';

export default function ProjectEdit({ project, projects, info }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [state, setState] = useState({});
  const [tools, setTools] = useState([]);
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const navigate = useNavigate();

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

    if (project.type === "rag" || project.type === "inference" || project.type === "ragsql" || project.type === "agent") {
      opts.system = state.system
    }

    //if (project.type === "ragsql") {
    //  opts.connection = connectionForm.current.value
    //  opts.tables = tablesForm.current.value
    //}

    if (project.type === "agent") {
      opts.options.tools = state.options.tools
    }

    if (project.type === "rag") {
      opts.options.colbert_rerank = state.options.colbert_rerank
      opts.options.llm_rerank = state.options.llm_rerank
      opts.options.score = parseFloat(state.options.score) || 0.0
      opts.options.k = parseInt(state.options.k) || 4
      opts.options.cache = state.options.cache
      opts.options.cache_threshold = parseFloat(state.options.cache_threshold) || 0

      if (opts.censorship.trim() === "") {
        delete opts.options.censorship;
      }
    }

    fetch(url + "/projects/" + project.id, {
      method: 'PATCH',
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
      .then(() => {
        navigate("/project/" + project.id);
      }).catch(err => {
        toast.error(err.toString());
      });
  }

  const fetchTools = () => {
    return fetch(url + "/tools/agent", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then((res) => res.json())
      .then((d) => {
        setTools(d)
      }).catch(err => {
        console.log(err.toString());
        toast.error("Error fetching Tools");
      });
  }

  const fetchUsers = () => {
    return fetch(url + "/users", { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
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
        setUsers(d.users);
      }).catch(err => {
        console.log(err.toString());
        toast.error("Error fetching Users");
      });
  }

  const fetchTeams = () => {
    return fetch(url + "/teams", {
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
        toast.error("Error fetching teams");
      });
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
        .then((teamData) => {
          // Update state with the full team object
          setState(prevState => ({
            ...prevState,
            team: teamData
          }));
        })
        .catch(err => {
          console.log("Error fetching team details:", err.toString());
          toast.error("Error loading team details");
        });
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
        cache_threshold: 0,
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

    // If the project has a team, fetch its complete details
    if (project && project.team && project.team.id) {
      fetch(url + "/teams/" + project.team.id, {
        headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token })
      })
        .then(response => {
          if (!response.ok) {
            throw Error(response.statusText);
          }
          return response.json();
        })
        .then(teamData => {
          // Update state with full team details, preserving other state properties
          setState(prevState => ({
            ...prevState,
            team: teamData
          }));
        })
        .catch(err => {
          console.log("Error fetching team details:", err.toString());
        });
    }
  }, [project, url, auth.user.token]);

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

            {state.llm !== undefined && (
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
                    .filter(item =>
                      state.type === "vision"
                        ? item.type === "vision"
                        : item.type !== "vision"
                    )
                    .map((item) => (
                      <MenuItem value={item.name} key={item.name}>
                        {item.name}
                      </MenuItem>
                    ))}
                </TextField>
              </Grid>
            )}

            {(state.type === "rag" || state.type === "inference" || state.type === "ragsql" || state.type === "agent") && (
              <Grid item sm={6} xs={12}>
                <TextField
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  name="system"
                  label="System Message"
                  variant="outlined"
                  onChange={handleChange}
                  value={state.system ?? ''}
                  multiline={true}
                />
              </Grid>
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
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="guard"
                label="Prompt Guard Project"
                variant="outlined"
                onChange={handleChange}
                value={state.guard ?? ''}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="censorship"
                label="Censhorship Message"
                variant="outlined"
                onChange={handleChange}
                value={state.censorship ?? ''}
              />
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
                  <FormControlLabel
                    label="Tools"
                    sx={{ ml: 0 }}
                    width="200px"
                    control={
                      <Autocomplete
                        multiple
                        id="tags-standard"
                        name="tools"
                        fullWidth
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
                            variant="standard"
                            label=""
                            placeholder=""
                          />
                        )}
                        sx={{ width: '200px' }}
                      />
                    }
                  />
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
                  <Typography id="discrete-slider" gutterBottom>
                    Cache Threshold
                  </Typography>
                  <Slider
                    name="cache_threshold"
                    value={(state.options?.cache_threshold ?? 0) * 100}
                    onChange={handleChange}
                    aria-labelledby="input-slider"
                    step={1}
                    min={0}
                    max={100}
                    valueLabelDisplay="auto"
                    style={{ width: "400px" }}
                  />
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
              <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/project/" + project.name) }}>
                Cancel
              </Button>
            </Grid>
          </Grid>
        </Box>
      </form>
    </Card>
  );
}
