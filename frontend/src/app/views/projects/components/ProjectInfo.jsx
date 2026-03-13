import {
  Card,
  Table,
  styled,
  Divider,
  TableRow,
  TableBody,
  TableCell,
  Switch,
  Button,
  Tooltip,
  Avatar,
  Box
} from "@mui/material";

import { H4, Small } from "app/components/Typography";
import { FlexBetween, FlexBox } from "app/components/FlexBox";
import { Edit } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { SportsEsports, Delete, Code, Article } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import sha256 from 'crypto-js/sha256';
import BAvatar from "boring-avatars";

const ContentBox = styled(FlexBox)({
  alignItems: "center",
  flexDirection: "column"
});

const StyledAvatar = styled(Avatar)(() => ({
  width: "32px !important",
  height: "32px !important"
}));

export default function ProjectInfo({ project, projects }) {
  const navigate = useNavigate();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();


  const handleDeleteClick = () => {
    if (window.confirm("Are you sure you to delete the project " + project.name + "?")) {
      fetch(url + "/projects/" + project.id, {
        method: 'DELETE',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      })
        .then(response => {
          if (!response.ok) {
            throw new Error('Error deleting project');
          }
          navigate("/projects");
        }).catch(err => {
          console.log(err.toString());
          toast.error("Error deleting project");
        });
    }
  };

  return (
    <Card sx={{ pt: 3 }} elevation={3}>
      <ContentBox mb={3} alignContent="center">
        <BAvatar name={project.name} size={84} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]}/>

        <H4 sx={{ mt: "16px", mb: "8px" }}>{project.name}</H4>
        <Small color="text.secondary">{project.type}</Small>
      </ContentBox>

      <Divider />

      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Name</TableCell>
            <TableCell>{project.human_name}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>ID</TableCell>
            <TableCell>{project.id}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Description</TableCell>
            <TableCell>{project.human_description}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Shared</TableCell>
            <TableCell>
              <Switch
                disabled
                checked={project.public ?? false}
                inputProps={{ "aria-label": "secondary checkbox" }}
              />
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Users</TableCell>
            <TableCell>
              <Box display="flex" alignItems="center" gap={1}>
                {(project.users || []).map((user, index) => (
                  <div key={user || index}>
                    <Tooltip title={user} placement="top">
                      <StyledAvatar src={"https://www.gravatar.com/avatar/" + sha256(user)} />
                    </Tooltip>
                  </div>
                ))}
                {(project.users || []).length >= 3 &&
                  <div>
                    <Tooltip title={project.users.slice(2).map(user => user).join(", ")} placement="top">
                      <StyledAvatar sx={{ fontSize: "14px" }}>+{project.users.length - 2}</StyledAvatar>
                    </Tooltip>
                  </div>
                }
              </Box>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <FlexBetween p={2}>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/edit") }} startIcon={<Edit fontSize="small" />}>
          Edit
        </Button>
        <Button variant="outlined" color="error" onClick={handleDeleteClick} startIcon={<Delete fontSize="small" />}>
          Delete
        </Button>
      </FlexBetween>
      <FlexBetween p={2} pt={0}>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/api") }} startIcon={<Code fontSize="small" />}>
          API
        </Button>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/playground") }} startIcon={<SportsEsports fontSize="small" />}>
          Playground
        </Button>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/logs") }} startIcon={<Article fontSize="small" />}>
          Logs
        </Button>
      </FlexBetween>
    </Card>
  );
}