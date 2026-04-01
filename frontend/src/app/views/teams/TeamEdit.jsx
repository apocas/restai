import { useState, useEffect } from "react";
import {
  Box,
  Grid,
  styled,
  Card,
  Typography,
  Button,
  TextField,
  Autocomplete,
  Divider,
  InputAdornment,
  Tabs,
  Tab
} from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { Breadcrumb } from "app/components";
import { toast } from 'react-toastify';
import { Group, Code, Psychology, Palette } from "@mui/icons-material";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" },
  "& .breadcrumb": {
    marginBottom: "30px",
    [theme.breakpoints.down("sm")]: { marginBottom: "16px" }
  }
}));

const StyledCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(3),
  marginBottom: theme.spacing(3)
}));

function TabPanel(props) {
  const { children, value, index, ...other } = props;

  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`team-tabpanel-${index}`}
      aria-labelledby={`team-tab-${index}`}
      {...other}
    >
      {value === index && <Box sx={{ p: 3 }}>{children}</Box>}
    </div>
  );
}

export default function TeamEdit() {
  const { id } = useParams();
  const isNewTeam = id === undefined;
  const [team, setTeam] = useState({
    name: "",
    description: "",
    budget: -1,
    users: [],
    admins: [],
    projects: [],
    llms: [],
    embeddings: [],
    image_generators: [],
    audio_generators: [],
    branding: { primary_color: "", secondary_color: "", logo_url: "", welcome_message: "", app_name: "" },
  });
  const [users, setUsers] = useState([]);
  const [projects, setProjects] = useState([]);
  const [llms, setLLMs] = useState([]);
  const [embeddings, setEmbeddings] = useState([]);
  const [imageGenerators, setImageGenerators] = useState([]);
  const [audioGenerators, setAudioGenerators] = useState([]);
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(true);
  const [inviteUsername, setInviteUsername] = useState("");

  const handleInvite = () => {
    if (!inviteUsername.trim()) return;
    api.post(`/teams/${id}/invitations`, { username: inviteUsername.trim() }, auth.user.token)
      .then((data) => {
        toast.success(data.message || "Invitation sent");
        setInviteUsername("");
      })
      .catch(() => {});
  };
  const navigate = useNavigate();
  const auth = useAuth();
  const user = auth.user;

  const fetchTeam = async () => {
    if (isNewTeam) {
      setLoading(false);
      return;
    }

    try {
      const data = await api.get(`/teams/${id}`, user.token);

      // Preprocess the data for form usage
      setTeam({
        ...data,
        users: data.users || [],
        admins: data.admins || [],
        projects: data.projects || [],
        llms: data.llms || [],
        embeddings: data.embeddings || [],
        image_generators: (data.image_generators || []).map(g => ({ name: g })),
        audio_generators: (data.audio_generators || []).map(g => ({ name: g })),
        branding: data.branding || { primary_color: "", secondary_color: "", logo_url: "", welcome_message: "", app_name: "" },
      });

      setLoading(false);
    } catch (error) {
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const data = await api.get("/users", user.token);
      setUsers(data.users);
    } catch (error) {
      // errors auto-toasted
    }
  };

  const fetchProjects = async () => {
    try {
      const data = await api.get("/projects", user.token);
      setProjects(data.projects);
    } catch (error) {
      // errors auto-toasted
    }
  };

  const fetchModels = async () => {
    try {
      const data = await api.get("/info", user.token);
      setLLMs(data.llms);
      setEmbeddings(data.embeddings);
    } catch (error) {
      // errors auto-toasted
    }
  };

  const fetchGenerators = async () => {
    try {
      const imgData = await api.get("/image", user.token, { silent: true });
      setImageGenerators((imgData.generators || []).map(g => ({ name: g })));
    } catch (error) {
      // GPU not enabled — keep empty, admin can still type free-form
    }
    try {
      const audioData = await api.get("/audio", user.token, { silent: true });
      setAudioGenerators((audioData.generators || []).map(g => ({ name: g })));
    } catch (error) {
      // GPU not enabled — keep empty, admin can still type free-form
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      await Promise.all([fetchTeam(), fetchUsers(), fetchProjects(), fetchModels(), fetchGenerators()]);
    };

    fetchData();
  }, [id]);

  useEffect(() => {
    document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - ${isNewTeam ? 'New Team' : 'Edit Team'}`;
  }, [isNewTeam]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setTeam({
      ...team,
      [name]: value
    });
  };

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    try {
      const payload = {
        name: team.name,
        description: team.description,
        budget: parseFloat(team.budget),
        users: team.users.map(u => u.username),
        admins: team.admins.map(a => a.username),
        projects: team.projects.map(p => p.name),
        llms: team.llms.map(l => l.name),
        embeddings: team.embeddings.map(e => e.name),
        image_generators: team.image_generators.map(g => g.name),
        audio_generators: team.audio_generators.map(g => g.name),
        branding: team.branding,
      };

      const endpoint = isNewTeam ? '/teams' : `/teams/${id}`;
      const data = isNewTeam
        ? await api.post(endpoint, payload, user.token)
        : await api.patch(endpoint, payload, user.token);

      toast.success(`Team ${isNewTeam ? 'created' : 'updated'} successfully`);

      // Redirect to the team view page
      navigate(isNewTeam ? `/team/${data.id}` : `/team/${id}`);
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleCancel = () => {
    navigate(isNewTeam ? '/teams' : `/team/${id}`);
  };

  if (loading) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[
            { name: "Teams", path: "/teams" },
            { name: isNewTeam ? "New Team" : "Edit Team", path: isNewTeam ? "/teams/new" : `/teams/${id}/edit` }
          ]} />
        </Box>
        <Typography>Loading...</Typography>
      </Container>
    );
  }

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[
          { name: "Teams", path: "/teams" },
          { name: isNewTeam ? "New Team" : "Edit Team", path: isNewTeam ? "/teams/new" : `/teams/${id}/edit` }
        ]} />
      </Box>

      <form onSubmit={handleSubmit}>
        <StyledCard>
          <Typography variant="h5" mb={3}>{isNewTeam ? 'Create New Team' : 'Edit Team'}</Typography>
          
          <Grid container spacing={3}>
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Team Name"
                name="name"
                value={team.name}
                onChange={handleChange}
                required
                variant="outlined"
              />
            </Grid>
            
            <Grid item xs={12}>
              <TextField
                fullWidth
                label="Description"
                name="description"
                value={team.description || ''}
                onChange={handleChange}
                multiline
                rows={3}
                variant="outlined"
              />
            </Grid>

            <Grid item xs={12} sm={6}>
              <TextField
                fullWidth
                label="Budget (-1 = unlimited)"
                name="budget"
                type="number"
                value={team.budget}
                onChange={handleChange}
                variant="outlined"
                helperText="Set to -1 for unlimited budget"
                inputProps={{ step: "0.01" }}
              />
            </Grid>
          </Grid>

          <Box sx={{ mt: 4, borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={tabValue} onChange={handleTabChange} aria-label="team tabs">
              <Tab label="Users" icon={<Group />} iconPosition="start" />
              <Tab label="Projects" icon={<Code />} iconPosition="start" />
              <Tab label="Models" icon={<Psychology />} iconPosition="start" />
              <Tab label="Branding" icon={<Palette />} iconPosition="start" />
            </Tabs>
          </Box>
          
          <TabPanel value={tabValue} index={0}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Team Members</Typography>
                <Autocomplete
                  multiple
                  id="users-select"
                  options={users}
                  getOptionLabel={(option) => option.username}
                  value={team.users}
                  onChange={(event, newValue) => {
                    setTeam({ ...team, users: newValue });
                  }}
                  filterSelectedOptions
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      variant="outlined"
                      label="Select Users"
                      placeholder="Users"
                    />
                  )}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Team Admins</Typography>
                <Autocomplete
                  multiple
                  id="admins-select"
                  options={users}
                  getOptionLabel={(option) => option.username}
                  value={team.admins}
                  onChange={(event, newValue) => {
                    setTeam({ ...team, admins: newValue });
                  }}
                  filterSelectedOptions
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      variant="outlined"
                      label="Select Admins"
                      placeholder="Admins"
                    />
                  )}
                />
                <Typography variant="caption" color="textSecondary">
                  Team admins can manage team settings and members
                </Typography>
              </Grid>

              <Grid item xs={12}>
                <Divider sx={{ my: 2 }} />
                <Typography variant="h6" gutterBottom>Invite User</Typography>
                <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 1 }}>
                  Send an invitation to a user by username. They will be able to accept or decline.
                </Typography>
                <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                  <TextField
                    size="small"
                    label="Username"
                    value={inviteUsername}
                    onChange={(e) => setInviteUsername(e.target.value)}
                    sx={{ width: 250 }}
                  />
                  <Button
                    variant="contained"
                    onClick={handleInvite}
                    disabled={!inviteUsername.trim()}
                  >
                    Send Invite
                  </Button>
                </Box>
              </Grid>
            </Grid>
          </TabPanel>
          
          <TabPanel value={tabValue} index={1}>
            <Typography variant="h6" gutterBottom>Team Projects</Typography>
            <Autocomplete
              multiple
              id="projects-select"
              options={projects}
              getOptionLabel={(option) => option.name}
              value={team.projects}
              onChange={(event, newValue) => {
                setTeam({ ...team, projects: newValue });
              }}
              filterSelectedOptions
              renderInput={(params) => (
                <TextField
                  {...params}
                  variant="outlined"
                  label="Select Projects"
                  placeholder="Projects"
                />
              )}
            />
            <Typography variant="caption" color="textSecondary">
              Projects assigned to this team will be accessible by all team members
            </Typography>
          </TabPanel>
          
          <TabPanel value={tabValue} index={2}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Team LLMs</Typography>
                <Autocomplete
                  multiple
                  id="llms-select"
                  options={llms}
                  getOptionLabel={(option) => option.name}
                  value={team.llms}
                  onChange={(event, newValue) => {
                    setTeam({ ...team, llms: newValue });
                  }}
                  filterSelectedOptions
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      variant="outlined"
                      label="Select LLMs"
                      placeholder="LLMs"
                    />
                  )}
                />
              </Grid>
              
              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Team Embedding Models</Typography>
                <Autocomplete
                  multiple
                  id="embeddings-select"
                  options={embeddings}
                  getOptionLabel={(option) => option.name}
                  value={team.embeddings}
                  onChange={(event, newValue) => {
                    setTeam({ ...team, embeddings: newValue });
                  }}
                  filterSelectedOptions
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      variant="outlined"
                      label="Select Embeddings"
                      placeholder="Embeddings"
                    />
                  )}
                />
              </Grid>

              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Image Generators</Typography>
                {imageGenerators.length > 0 ? (
                  <Autocomplete
                    multiple
                    id="image-generators-select"
                    options={imageGenerators}
                    getOptionLabel={(option) => option.name}
                    value={team.image_generators}
                    onChange={(event, newValue) => {
                      setTeam({ ...team, image_generators: newValue });
                    }}
                    isOptionEqualToValue={(option, value) => option.name === value.name}
                    filterSelectedOptions
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        variant="outlined"
                        label="Select Image Generators"
                        placeholder="Image Generators"
                      />
                    )}
                  />
                ) : (
                  <Typography variant="body2" color="textSecondary">
                    No image generators available. GPU may not be enabled on this instance.
                  </Typography>
                )}
              </Grid>

              <Grid item xs={12} md={6}>
                <Typography variant="h6" gutterBottom>Audio Generators</Typography>
                {audioGenerators.length > 0 ? (
                  <Autocomplete
                    multiple
                    id="audio-generators-select"
                    options={audioGenerators}
                    getOptionLabel={(option) => option.name}
                    value={team.audio_generators}
                    onChange={(event, newValue) => {
                      setTeam({ ...team, audio_generators: newValue });
                    }}
                    isOptionEqualToValue={(option, value) => option.name === value.name}
                    filterSelectedOptions
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        variant="outlined"
                        label="Select Audio Generators"
                        placeholder="Audio Generators"
                      />
                    )}
                  />
                ) : (
                  <Typography variant="body2" color="textSecondary">
                    No audio generators available. GPU may not be enabled on this instance.
                  </Typography>
                )}
              </Grid>
            </Grid>
          </TabPanel>

          <TabPanel value={tabValue} index={3}>
            <Typography variant="h6" gutterBottom>White-Label Branding</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Customize the platform appearance for team members. Leave fields empty to use platform defaults.
            </Typography>
            <Grid container spacing={3}>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="App Name"
                  value={team.branding?.app_name || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, app_name: e.target.value } })}
                  variant="outlined"
                  helperText="Overrides the platform name in the sidebar"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Logo URL"
                  value={team.branding?.logo_url || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, logo_url: e.target.value } })}
                  variant="outlined"
                  helperText="URL or data:image/... URI for the sidebar logo"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Primary Color"
                  value={team.branding?.primary_color || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, primary_color: e.target.value } })}
                  variant="outlined"
                  placeholder="#1976d2"
                  helperText="Hex color for header and primary elements"
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <input
                          type="color"
                          value={team.branding?.primary_color || "#1976d2"}
                          onChange={(e) => setTeam({ ...team, branding: { ...team.branding, primary_color: e.target.value } })}
                          style={{ width: 32, height: 32, padding: 0, border: "none", cursor: "pointer", background: "none" }}
                        />
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  label="Secondary Color"
                  value={team.branding?.secondary_color || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, secondary_color: e.target.value } })}
                  variant="outlined"
                  placeholder="#ff9800"
                  helperText="Hex color for accents and secondary elements"
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <input
                          type="color"
                          value={team.branding?.secondary_color || "#ff9800"}
                          onChange={(e) => setTeam({ ...team, branding: { ...team.branding, secondary_color: e.target.value } })}
                          style={{ width: 32, height: 32, padding: 0, border: "none", cursor: "pointer", background: "none" }}
                        />
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  multiline
                  rows={3}
                  label="Welcome Message"
                  value={team.branding?.welcome_message || ""}
                  onChange={(e) => setTeam({ ...team, branding: { ...team.branding, welcome_message: e.target.value } })}
                  variant="outlined"
                  helperText="Displayed on the landing page for team members"
                />
              </Grid>

              {/* Live preview */}
              {(team.branding?.logo_url || team.branding?.primary_color || team.branding?.app_name) && (
                <Grid item xs={12}>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>Preview</Typography>
                  <Box sx={{
                    display: "flex", alignItems: "center", gap: 1.5, p: 2,
                    bgcolor: team.branding?.primary_color || "primary.main",
                    borderRadius: 1, color: "#fff",
                  }}>
                    {team.branding?.logo_url ? (
                      <img width="30" height="30" src={team.branding.logo_url} alt="logo" style={{ objectFit: "contain" }} />
                    ) : (
                      <img width="30" height="30" src="/admin/assets/images/restai-logo.png" alt="logo" />
                    )}
                    <Typography variant="h6" sx={{ color: "#fff" }}>
                      {team.branding?.app_name || team.name || "RESTai"}
                    </Typography>
                  </Box>
                </Grid>
              )}
            </Grid>
          </TabPanel>

          <Box mt={4} display="flex" justifyContent="flex-end">
            <Button
              variant="outlined"
              color="secondary"
              onClick={handleCancel}
              sx={{ mr: 2 }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              variant="contained"
              color="primary"
            >
              {isNewTeam ? 'Create Team' : 'Save Changes'}
            </Button>
          </Box>
        </StyledCard>
      </form>
    </Container>
  );
}