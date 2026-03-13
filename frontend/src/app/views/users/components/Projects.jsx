import {
  Box,
  Card,
  Grid,
  Button,
  Divider,
  TextField,
  styled,
  MenuItem
} from "@mui/material";
import { useState } from "react";
import { H5, Paragraph } from "app/components/Typography";
import { FlexBetween, FlexBox } from "app/components/FlexBox";
import { convertHexToRGB } from "app/utils/utils";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import BAvatar from "boring-avatars";

export default function Preferences({ user, projects }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [state, setState] = useState({});

  const StyledP = styled(Paragraph)(({ theme }) => ({
    color: theme.palette.text.secondary,
  }));

  const StyledButton = styled(Button)(({ theme }) => ({
    paddingLeft: "20px",
    paddingRight: "20px",
    transition: "all 250ms",
    color: theme.palette.error.main,
    background: `rgba(${convertHexToRGB(theme.palette.error.main)}, 0.15)`,
    "&:hover": {
      color: "#ffffff",
      fallbacks: [{ color: "white !important" }],
      background: `${theme.palette.error.main} !important`,
      backgroundColor: `${theme.palette.error.main} !important`,
    },
  }));

  const projectMap = projects.reduce((acc, p) => {
    acc[p.id] = p;
    return acc;
  }, {});

  const userProjectsDetailed = user.projects.map((p) => ({
    ...p,
    ...projectMap[p.id],
  }));

  const diassoc = (project) => {
    var updatedProjects = user.projects.filter((p) => p.id !== project.id);
    user.projects = updatedProjects;
    onSubmitHandler();
  }

  const onSubmitHandler = (event) => {
    if (event)
      event.preventDefault();

    fetch(url + "/users/" + user.username, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      body: JSON.stringify({
        "projects": user.projects.map((p) => {
          // Try to get name from the project object or from the projectMap
          const projectName = p.name || (projectMap[p.id] && projectMap[p.id].name);
          return projectName;
        }).filter(name => name != null) // Filter out null/undefined values
      }),
    })
      .then(response => {
        window.location.href = "/admin/user/" + user.username;
      }).catch(err => {
        toast.error(err.toString());
      });

  }

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
  };

  return (
    <Card>
      <H5 padding={3}>General Preferences</H5>
      <Divider />

      <Box margin={3}>
        {auth.user.is_admin === true &&
          <Grid container spacing={3}>
            <Grid item sm={6} xs={12}>
              <TextField
                select
                size="small"
                name="addproject"
                label="Project"
                variant="outlined"
                value={state.addproject ?? ''}
                onChange={handleChange}
                sx={{ minWidth: 188 }}
              >
                {projects.map((item, ind) => (
                  <MenuItem value={item.name} key={item.name}>
                    {item.name} (ID: {item.id})
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item sm={6} xs={12}>
              <Button type="submit" variant="contained" mt={1} onClick={() => { 
                const selectedProject = projects.find(p => p.name === state.addproject);
                if (selectedProject) {
                  user.projects.push({ "name": selectedProject.name, "id": selectedProject.id }); 
                  onSubmitHandler();
                }
              }}>
                Associate
              </Button>
            </Grid>
          </Grid>
        }
      </Box>
      <Divider />
      <Box margin={3}>
        <Grid container spacing={3}>
          {userProjectsDetailed.map((project) => (
            <Grid item sm={6} xs={12} key={project.id}>
              <Card>
                <FlexBetween p="24px" m={-1} flexWrap="wrap">
                  <FlexBox alignItems="center" m={1}>
                    <BAvatar name={project.name} size={55} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]} square/>

                    <Box ml={2}>
                      <H5>{project.name} <span style={{fontWeight: 'normal', fontSize: '0.9em', color: '#888'}}> (ID: {project.id})</span></H5>
                      <StyledP sx={{ mt: 1, fontWeight: "normal", textTransform: "capitalize" }}>
                        {(project.human_name || "").toLowerCase()}
                      </StyledP>
                    </Box>
                  </FlexBox>

                  {auth.user.is_admin === true &&
                    <Box m={1} display="flex">
                      <StyledButton size="small" onClick={() => { diassoc(project) }} >Dissociate</StyledButton>
                    </Box>
                  }
                </FlexBetween>
              </Card>
            </Grid>
          ))}
        </Grid>
      </Box>
    </Card>
  );
}
