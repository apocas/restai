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
import api from "app/utils/api";

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

  const fetchTeams = async () => {
    try {
      const data = await api.get("/teams", user.token);
      setTeams(data.teams);
    } catch (error) {
      // errors auto-toasted
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
      await api.delete(`/teams/${teamId}`, user.token);
      toast.success("Team deleted successfully");
      fetchTeams();
    } catch (error) {
      // errors auto-toasted
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