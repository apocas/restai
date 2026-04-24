import { useState, useEffect } from "react";
import { Grid, styled, Box } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import LLMEdit from "./components/LLMEdit";
import Breadcrumb from "app/components/Breadcrumb";
import { useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
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


export default function LLMEditView() {
  const { t } = useTranslation();
  const { id } = useParams();
  const [llm, setLLM] = useState({});
  const auth = useAuth();


  const fetchLLM = (llm) => {
    return api.get("/llms/" + llm, auth.user.token)
      .then((d) => {
        setLLM(d)
        return d
      }).catch(() => {});
  }

  useEffect(() => {
    fetchLLM(id);
  }, [id]);


  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.llms"), path: "/llms"}, { name: t("common.edit") + " " + id, path: "/llm/" + id + "/edit" }]} />
      </Box>

      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid item lg={12} md={8} sm={12} xs={12}>
            <LLMEdit llm={llm} />
          </Grid>
        </Grid>
      </ContentBox>
    </Container>
  );
}
