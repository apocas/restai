import { Card, Divider, Box, Grid, TextField, Button } from "@mui/material";
import { H4 } from "app/components/Typography";
import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import { useNavigate } from "react-router-dom";

export default function EmbeddingEdit({ embedding }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
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

    fetch(url + "/embeddings/" + embedding.name, {
      method: 'PATCH',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      body: JSON.stringify(update),
    }).then(function (response) {
      if (!response.ok) {
        response.json().then(function (data) {
          toast.error(data.detail);
        });
        throw Error(response.statusText);
      } else {
        return response.json();
      }
    }).then(response => {
      window.location.href = "/admin/embedding/" + embedding.name;
    }).catch(err => {
      console.log(err.toString());
      toast.error("Error updating embedding");
    });
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
      <H4 p={2}>Edit Embedding - {embedding.name}</H4>

      <Divider sx={{ mb: 1 }} />

      <form onSubmit={handleSubmit}>
        <Box margin={3}>
          <Grid container spacing={3}>
            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="name"
                label="Name"
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
                label="Class Name"
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
                label="Options"
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
                label="Privacy"
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
                label="Description"
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
                label="Dimension"
                variant="outlined"
                onChange={handleChange}
                value={state.dimension}
              />
            </Grid>

            <Grid item xs={12}>
              <Button type="submit" variant="contained">
                Save Changes
              </Button>
              <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/embeddings") }}>
                Cancel
              </Button>
            </Grid>
          </Grid>
        </Box>
      </form>
    </Card>
  );
}
