import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import UsersTable from "../dashboard/shared/UsersTable";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import api from "app/utils/api";

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

export default function Users() {
  const [users, setUsers] = useState([]);
  const auth = useAuth();

  const fetchUsers = () => {
    return api.get("/users", auth.user.token)
      .then((d) => setUsers(d.users))
      .catch(() => {});
  };

  const handleDelete = (username) => {
    if (!window.confirm(`Are you sure you want to delete user "${username}"?`)) return;
    api.delete("/users/" + username, auth.user.token)
      .then(() => fetchUsers())
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Users';
    fetchUsers();
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Users", path: "/users" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <UsersTable users={users} onDelete={handleDelete} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
