import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import ToolsTable from "../dashboard/shared/ToolsTable";
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


export default function Tools() {
  const [tools, setTools] = useState([]);
  const auth = useAuth();

  const fetchTools = () => {
    return api.get("/tools/agent", auth.user.token)
      .then((d) => {
        setTools(d)
      })
      .catch(() => {});
  }
  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Projects';
    fetchTools();
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Projects", path: "/projects" }, { name: "Tools", path: "/projects/tools" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <ToolsTable tools={tools} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
