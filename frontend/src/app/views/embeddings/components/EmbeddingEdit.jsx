import { Card, Divider, Box, Grid, TextField, Button } from "@mui/material";
import { H4 } from "app/components/Typography";
import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

export default function EmbeddingEdit({ embedding }) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [state, setState] = useState({});
  const navigate = useNavigate();

  const handleSubmit = (event) => {
    event.preventDefault();

    var update = {};

    if (state.name !== embedding.name) {
      update.name = state.name;
    }
    if (state.class_name !== embedding.class_name) {
      update.class_name = state.class_name;
    }
    if (state.options !== embedding.options) {
      update.options = state.options;
    }
    if (state.privacy !== embedding.privacy) {
      update.privacy = state.privacy;
    }
    if (state.description !== embedding.description) {
      update.description = state.description;
    }
    if (state.dimension !== embedding.dimension) {
      update.dimension = state.dimension;
    }

    api.patch("/embeddings/" + embedding.id, update, auth.user.token)
      .then(() => {
        window.location.href = "/admin/embedding/" + embedding.id;
      }).catch(() => {});
  }


  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  useEffect(() => {
    setState(embedding);
  }, [embedding]);

  return (
    <Card elevation={3}>
      <H4 p={2}>{t("embeddings.edit.title", { name: embedding.name })}</H4>

      <Divider sx={{ mb: 1 }} />

      <form onSubmit={handleSubmit}>
        <Box margin={3}>
          <Grid container spacing={3}>
            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="name"
                label={t("embeddings.edit.name")}
                variant="outlined"
                onChange={handleChange}
                value={state.name}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="class_name"
                label={t("embeddings.edit.className")}
                variant="outlined"
                onChange={handleChange}
                value={state.class_name}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="options"
                label={t("embeddings.edit.options")}
                variant="outlined"
                onChange={handleChange}
                value={state.options}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="privacy"
                label={t("embeddings.edit.privacy")}
                variant="outlined"
                onChange={handleChange}
                value={state.privacy}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="description"
                label={t("embeddings.edit.description")}
                variant="outlined"
                onChange={handleChange}
                value={state.description}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="dimension"
                label={t("embeddings.edit.dimension")}
                variant="outlined"
                onChange={handleChange}
                value={state.dimension}
              />
            </Grid>

            <Grid item xs={12}>
              <Button type="submit" variant="contained">
                {t("embeddings.edit.saveChanges")}
              </Button>
              <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/embeddings") }}>
                {t("common.cancel")}
              </Button>
            </Grid>
          </Grid>
        </Box>
      </form>
    </Card>
  );
}
