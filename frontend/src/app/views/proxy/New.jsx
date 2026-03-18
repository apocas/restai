import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import KeyNew from "./components/KeyNew";
import Breadcrumb from "app/components/Breadcrumb";
import api from "app/utils/api";


const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));


export default function ProjectNewView() {
  const [info, setInfo] = useState({ "models": [], "url": "" });
  const auth = useAuth();


  const fetchInfo = () => {
    return api.get("/proxy/info", auth.user.token)
      .then((d) => setInfo(d))
      .catch(() => {});
  }

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - New Proxy API Key';
    fetchInfo();
  }, []);


  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Proxy", path: "/proxy" }, { name: "New Key", path: "/proxy/keys/new" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <KeyNew info={info} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
