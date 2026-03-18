import { useState, useEffect, Fragment } from "react";
import {
  Box,
  Grid,
  styled,
  Card,
  Typography,
  Button,
  Tabs,
  Tab,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Avatar,
  Divider,
  IconButton,
  Tooltip
} from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { Breadcrumb } from "app/components";
import { toast } from 'react-toastify';
import { Person, Settings, Delete, Group, Code, Psychology } from "@mui/icons-material";
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

export default function TeamView() {
  const { id } = useParams();
  const [team, setTeam] = useState(null);
  const [tabValue, setTabValue] = useState(0);
  const navigate = useNavigate();
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);

  const isTeamAdmin = team?.admins?.some(admin => admin.id === user.id) || user.is_admin;

  const fetchTeam = async () => {
    setLoading(true);
    try {
      const data = await api.get(`/teams/${id}`, user.token);
      setTeam(data);
    } catch (error) {
      // errors auto-toasted
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTeam();
  }, [id]);

  useEffect(() => {
    if (team) {
      document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - Team: ${team.name}`;
    }
  }, [team]);

  const handleTabChange = (event, newValue) => {
    setTabValue(newValue);
  };

  const handleEditTeam = () => {
    navigate(`/team/${id}/edit`);
  };

  const handleRemoveUser = async (username) => {
    if (!window.confirm(`Are you sure you want to remove ${username} from this team?`)) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/users/${username}`, user.token);
      toast.success(`${username} removed from team`);
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveAdmin = async (username) => {
    if (!window.confirm(`Are you sure you want to remove admin privileges from ${username}?`)) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/admins/${username}`, user.token);
      toast.success(`Admin privileges removed from ${username}`);
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveProject = async (projectId) => {
    if (!window.confirm("Are you sure you want to remove this project from the team?")) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/projects/${projectId}`, user.token);
      toast.success("Project removed from team");
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveLLM = async (llmName) => {
    if (!window.confirm(`Are you sure you want to remove ${llmName} from this team?`)) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/llms/${llmName}`, user.token);
      toast.success(`${llmName} removed from team`);
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  const handleRemoveEmbedding = async (embeddingName) => {
    if (!window.confirm(`Are you sure you want to remove ${embeddingName} from this team?`)) {
      return;
    }

    try {
      await api.delete(`/teams/${id}/embeddings/${embeddingName}`, user.token);
      toast.success(`${embeddingName} removed from team`);
      fetchTeam();
    } catch (error) {
      // errors auto-toasted
    }
  };

  if (loading) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[
            { name: "Teams", path: "/teams" },
            { name: "Loading...", path: `/teams/${id}` }
          ]} />
        </Box>
        <Typography>Loading team details...</Typography>
      </Container>
    );
  }

  if (!team) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb routeSegments={[
            { name: "Teams", path: "/teams" },
            { name: "Not Found", path: `/teams/${id}` }
          ]} />
        </Box>
        <Typography>Team not found or you don't have permission to view it.</Typography>
      </Container>
    );
  }

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[
          { name: "Teams", path: "/teams" },
          { name: team.name, path: `/teams/${id}` }
        ]} />
      </Box>

      <StyledCard>
        <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
          <Box>
            <Typography variant="h4">{team.name}</Typography>
            <Typography variant="body1" color="textSecondary">
              {team.description || "No description provided"}
            </Typography>
          </Box>
          {isTeamAdmin && (
            <Button
              variant="contained"
              color="primary"
              startIcon={<Settings />}
              onClick={handleEditTeam}
            >
              Edit Team
            </Button>
          )}
        </Box>
        
        <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
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
              <List>
                {team.users?.length > 0 ? (
                  team.users.map((member) => (
                    <Fragment key={member.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title="Remove User">
                            <IconButton edge="end" onClick={() => handleRemoveUser(member.username)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Person />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={member.username} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">No team members</Typography>
                )}
              </List>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>Team Admins</Typography>
              <List>
                {team.admins?.length > 0 ? (
                  team.admins.map((admin) => (
                    <Fragment key={admin.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title="Remove Admin Privileges">
                            <IconButton edge="end" onClick={() => handleRemoveAdmin(admin.username)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Person />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText 
                          primary={admin.username} 
                          secondary={admin.id === user.id ? "(You)" : ""}
                        />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">No team admins</Typography>
                )}
              </List>
            </Grid>
          </Grid>
        </TabPanel>
        
        <TabPanel value={tabValue} index={1}>
          <Typography variant="h6" gutterBottom>Team Projects</Typography>
          <List>
            {team.projects?.length > 0 ? (
              team.projects.map((project) => (
                <Fragment key={project.id}>
                  <ListItem 
                    button
                    onClick={() => navigate(`/project/${project.id}`)}
                    secondaryAction={
                      isTeamAdmin && (
                        <Tooltip title="Remove Project">
                          <IconButton edge="end" onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveProject(project.id);
                          }}>
                            <Delete />
                          </IconButton>
                        </Tooltip>
                      )
                    }
                  >
                    <ListItemAvatar>
                      <Avatar>
                        <Code />
                      </Avatar>
                    </ListItemAvatar>
                    <ListItemText primary={project.name} />
                  </ListItem>
                  <Divider variant="inset" component="li" />
                </Fragment>
              ))
            ) : (
              <Typography variant="body2" color="textSecondary">No projects assigned to this team</Typography>
            )}
          </List>
        </TabPanel>
        
        <TabPanel value={tabValue} index={2}>
          <Grid container spacing={3}>
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>Team LLMs</Typography>
              <List>
                {team.llms?.length > 0 ? (
                  team.llms.map((llm) => (
                    <Fragment key={llm.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title="Remove LLM">
                            <IconButton edge="end" onClick={() => handleRemoveLLM(llm.name)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Psychology />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={llm.name} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">No LLMs assigned to this team</Typography>
                )}
              </List>
            </Grid>
            
            <Grid item xs={12} md={6}>
              <Typography variant="h6" gutterBottom>Team Embedding Models</Typography>
              <List>
                {team.embeddings?.length > 0 ? (
                  team.embeddings.map((embedding) => (
                    <Fragment key={embedding.id}>
                      <ListItem secondaryAction={
                        isTeamAdmin && (
                          <Tooltip title="Remove Embedding">
                            <IconButton edge="end" onClick={() => handleRemoveEmbedding(embedding.name)}>
                              <Delete />
                            </IconButton>
                          </Tooltip>
                        )
                      }>
                        <ListItemAvatar>
                          <Avatar>
                            <Psychology />
                          </Avatar>
                        </ListItemAvatar>
                        <ListItemText primary={embedding.name} />
                      </ListItem>
                      <Divider variant="inset" component="li" />
                    </Fragment>
                  ))
                ) : (
                  <Typography variant="body2" color="textSecondary">No embedding models assigned to this team</Typography>
                )}
              </List>
            </Grid>
          </Grid>
        </TabPanel>
      </StyledCard>
    </Container>
  );
}