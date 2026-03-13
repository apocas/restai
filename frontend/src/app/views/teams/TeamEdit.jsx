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
  Tabs,
  Tab
} from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { Breadcrumb } from "app/components";
import { toast } from 'react-toastify';
import { Group, Code, Psychology } from "@mui/icons-material";

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
    users: [],
    admins: [],
    projects: [],
    llms: [],
    embeddings: []
  });
  const [users, setUsers] = useState([]);
  const [projects, setProjects] = useState([]);
  const [llms, setLLMs] = useState([]);
  const [embeddings, setEmbeddings] = useState([]);
  const [tabValue, setTabValue] = useState(0);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const { user } = useAuth();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";

  const fetchTeam = async () => {
    if (isNewTeam) {
      setLoading(false);
      return;
    }

    try {
      const response = await fetch(`${url}/teams/${id}`, {
        headers: new Headers({ 'Authorization': 'Basic ' + user.token }),
      });

      if (!response.ok) {
        const error = await response.json();
        toast.error(error.detail || "Failed to fetch team details");
        return;
      }

      const data = await response.json();
      
      // Preprocess the data for form usage
      setTeam({
        ...data,
        users: data.users || [],
        admins: data.admins || [],
        projects: data.projects || [],
        llms: data.llms || [],
        embeddings: data.embeddings || []
      });
      
      setLoading(false);
    } catch (error) {
      console.error("Error fetching team:", error);
      toast.error("Error fetching team details");
      setLoading(false);
    }
  };

  const fetchUsers = async () => {
    try {
      const response = await fetch(`${url}/users`, {
        headers: new Headers({ 'Authorization': 'Basic ' + user.token }),
      });

      if (!response.ok) {
        const error = await response.json();
        toast.error(error.detail || "Failed to fetch users");
        return;
      }

      const data = await response.json();
      setUsers(data.users);
    } catch (error) {
      console.error("Error fetching users:", error);
      toast.error("Error fetching users");
    }
  };

  const fetchProjects = async () => {
    try {
      const response = await fetch(`${url}/projects`, {
        headers: new Headers({ 'Authorization': 'Basic ' + user.token }),
      });

      if (!response.ok) {
        const error = await response.json();
        toast.error(error.detail || "Failed to fetch projects");
        return;
      }

      const data = await response.json();
      setProjects(data.projects);
    } catch (error) {
      console.error("Error fetching projects:", error);
      toast.error("Error fetching projects");
    }
  };

  const fetchModels = async () => {
    try {
      const response = await fetch(`${url}/info`, {
        headers: new Headers({ 'Authorization': 'Basic ' + user.token }),
      });

      if (!response.ok) {
        const error = await response.json();
        toast.error(error.detail || "Failed to fetch models");
        return;
      }

      const data = await response.json();
      setLLMs(data.llms);
      setEmbeddings(data.embeddings);
    } catch (error) {
      console.error("Error fetching models:", error);
      toast.error("Error fetching models");
    }
  };

  useEffect(() => {
    const fetchData = async () => {
      await Promise.all([fetchTeam(), fetchUsers(), fetchProjects(), fetchModels()]);
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
        users: team.users.map(u => u.username),
        admins: team.admins.map(a => a.username),
        projects: team.projects.map(p => p.name),
        llms: team.llms.map(l => l.name),
        embeddings: team.embeddings.map(e => e.name)
      };

      const method = isNewTeam ? 'POST' : 'PATCH';
      const endpoint = isNewTeam ? '/teams' : `/teams/${id}`;
      
      const response = await fetch(`${url}${endpoint}`, {
        method,
        headers: new Headers({
          'Content-Type': 'application/json',
          'Authorization': 'Basic ' + user.token 
        }),
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const error = await response.json();
        toast.error(error.detail || `Failed to ${isNewTeam ? 'create' : 'update'} team`);
        return;
      }

      const data = await response.json();
      toast.success(`Team ${isNewTeam ? 'created' : 'updated'} successfully`);
      
      // Redirect to the team view page
      navigate(isNewTeam ? `/team/${data.id}` : `/team/${id}`);
    } catch (error) {
      console.error(`Error ${isNewTeam ? 'creating' : 'updating'} team:`, error);
      toast.error(`Error ${isNewTeam ? 'creating' : 'updating'} team`);
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
          </Grid>

          <Box sx={{ mt: 4, borderBottom: 1, borderColor: 'divider' }}>
            <Tabs value={tabValue} onChange={handleTabChange} aria-label="team tabs">
              <Tab label="Users" icon={<Group />} iconPosition="start" />
              <Tab label="Projects" icon={<Code />} iconPosition="start" />
              <Tab label="Models" icon={<Psychology />} iconPosition="start" />
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