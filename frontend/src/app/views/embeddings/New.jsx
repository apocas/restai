import { useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import EmbeddingNew from "./components/EmbeddingNew";
import Breadcrumb from "app/components/Breadcrumb";


const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));


export default function EmbeddingNewView() {
  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - New LLM';
  }, []);


  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "LLMs", path: "/embeddings" }, { name: "New LLM", path: "/embedding/new" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <EmbeddingNew />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
