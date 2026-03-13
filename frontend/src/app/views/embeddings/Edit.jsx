import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import EmbeddingEdit from "./components/EmbeddingEdit";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import { toast } from 'react-toastify';

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));


export default function EmbeddingEditView() {
  const { id } = useParams();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const [embedding, setEmbedding] = useState({});
  const auth = useAuth();


  const fetchLLM = (llm) => {
    return fetch(url + "/embeddings/" + llm, { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then((res) => res.json())
      .then((d) => {
        setEmbedding(d)
        return d
      }).catch(err => {
        toast.error(err.toString());
      });
  }

  useEffect(() => {
    fetchLLM(id);
  }, [id]);


  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Embeddings", path: "/embeddings"}, { name: "Edit " + id, path: "/embedding/" + id + "/edit" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <EmbeddingEdit embedding={embedding} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
