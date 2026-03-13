import { useState, useEffect } from "react";
import {
  Box,
  Button,
  Grid,
  styled,
  IconButton,
  Icon,
  Tooltip,
  Chip
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import { Breadcrumb } from "app/components";
import TeamTable from "./components/TeamTable";
import { toast } from 'react-toastify';

const Container = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" },
  "& .breadcrumb": {
    marginBottom: "30px",
    [theme.breakpoints.down("sm")]: { marginBottom: "16px" }
  }
}));

const StyledButton = styled(Button)(({ theme }) => ({
  marginBottom: "16px",
}));

export default function Teams() {
  const [teams, setTeams] = useState([]);
  const navigate = useNavigate();
  const { user } = useAuth();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";

  const fetchTeams = async () => {
    try {
      const response = await fetch(`${url}/teams`, {
        headers: new Headers({ 'Authorization': 'Basic ' + user.token }),
      });

      if (!response.ok) {
        const error = await response.json();
        toast.error(error.detail || "Failed to fetch teams");
        return;
      }

      const data = await response.json();
      setTeams(data.teams);
    } catch (error) {
      console.error("Error fetching teams:", error);
      toast.error("Error fetching teams");
    }
  };

  useEffect(() => {
    fetchTeams();
    document.title = `${process.env.REACT_APP_RESTAI_NAME || "RESTai"} - Teams`;
  }, []);

  const handleNewTeam = () => {
    navigate("/teams/new");
  };

  const handleViewTeam = (teamId) => {
    navigate(`/team/${teamId}`);
  };

  const handleEditTeam = (teamId) => {
    navigate(`/team/${teamId}/edit`);
  };

  const handleDeleteTeam = async (teamId) => {
    if (!window.confirm("Are you sure you want to delete this team?")) {
      return;
    }

    try {
      const response = await fetch(`${url}/teams/${teamId}`, {
        method: 'DELETE',
        headers: new Headers({ 'Authorization': 'Basic ' + user.token }),
      });

      if (!response.ok) {
        const error = await response.json();
        toast.error(error.detail || "Failed to delete team");
        return;
      }

      toast.success("Team deleted successfully");
      fetchTeams();
    } catch (error) {
      console.error("Error deleting team:", error);
      toast.error("Error deleting team");
    }
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Teams", path: "/teams" }]} />
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12}>
          <TeamTable
            teams={teams}
            onView={handleViewTeam}
            onEdit={handleEditTeam}
            onDelete={handleDeleteTeam}
            isAdmin={user.is_admin}
          />
        </Grid>
      </Grid>
    </Container>
  );
}