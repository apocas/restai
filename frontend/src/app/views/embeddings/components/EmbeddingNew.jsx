import { useState } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  Box,
  Button,
  Card,
  Divider,
  Grid,
  MenuItem,
  styled,
  TextField
} from "@mui/material";
import { H4 } from "app/components/Typography";
import api from "app/utils/api";

const Form = styled("form")(() => ({ padding: "16px" }));

export default function EmbeddingNew({ projects, info }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const navigate = useNavigate();

  const [state, setState] = useState({});

  const handleSubmit = async (event) => {
    event.preventDefault();

    api.post("/embeddings", {
      "name": state.name,
      "class_name": state.class,
      "options": state.options,
      "privacy": state.privacy,
      "description": state.description
    }, auth.user.token)
      .then((response) => {
        navigate("/embedding/" + response.id);
      }).catch(() => {});

  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  return (
    <Card elevation={3}>
      <H4 p={2}>{t("embeddings.newCardTitle")}</H4>

      <Divider sx={{ mb: 1 }} />

      <Form onSubmit={handleSubmit}>
        <Grid container spacing={3} alignItems="center">
          <Grid item md={2} sm={4} xs={12}>
            {t("embeddings.edit.name")}
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="name"
              variant="outlined"
              label={t("embeddings.edit.name")}
              onChange={handleChange}
            />
          </Grid>

          <Grid item md={2} sm={4} xs={12}>
            {t("embeddings.edit.className")}
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="class"
              variant="outlined"
              label={t("embeddings.edit.className")}
              onChange={handleChange}
            />
          </Grid>

          <Grid item md={2} sm={4} xs={12}>
            {t("embeddings.edit.privacy")}
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              select
              size="small"
              name="privacy"
              label={t("embeddings.edit.privacy")}
              variant="outlined"
              onChange={handleChange}
              sx={{ minWidth: 188 }}
            >
              {["public", "private"].map((item, ind) => (
                <MenuItem value={item} key={item}>
                  {item}
                </MenuItem>
              ))}
            </TextField>
          </Grid>


          <Grid item md={2} sm={4} xs={12}>
            {t("embeddings.edit.options")}
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="options"
              variant="outlined"
              label={t("embeddings.edit.options")}
              onChange={handleChange}
            />
          </Grid>


          <Grid item md={2} sm={4} xs={12}>
            {t("embeddings.edit.description")}
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="description"
              variant="outlined"
              label={t("embeddings.edit.description")}
              onChange={handleChange}
            />
          </Grid>

          <Grid item md={2} sm={4} xs={12}>
            {t("embeddings.edit.dimension")}
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="dimension"
              variant="outlined"
              label={t("embeddings.edit.dimension")}
              onChange={handleChange}
            />
          </Grid>

        </Grid>

        <Box mt={3}>
          <Button color="primary" variant="contained" type="submit">
            {t("embeddings.submit")}
          </Button>
        </Box>
      </Form>
    </Card>
  );
}
