import { useState } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
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
        navigate("/embedding/" + response.name);
      }).catch(() => {});

  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  return (
    <Card elevation={3}>
      <H4 p={2}>Add a New Embedding</H4>

      <Divider sx={{ mb: 1 }} />

      <Form onSubmit={handleSubmit}>
        <Grid container spacing={3} alignItems="center">
          <Grid item md={2} sm={4} xs={12}>
            Name
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="name"
              variant="outlined"
              label="Name"
              onChange={handleChange}
            />
          </Grid>

          <Grid item md={2} sm={4} xs={12}>
            Class Name
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="class"
              variant="outlined"
              label="Class Name"
              onChange={handleChange}
            />
          </Grid>

          <Grid item md={2} sm={4} xs={12}>
            Privacy
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              select
              size="small"
              name="privacy"
              label="Privacy"
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
            Options
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="options"
              variant="outlined"
              label="Options"
              onChange={handleChange}
            />
          </Grid>


          <Grid item md={2} sm={4} xs={12}>
            Description
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="description"
              variant="outlined"
              label="Description"
              onChange={handleChange}
            />
          </Grid>

          <Grid item md={2} sm={4} xs={12}>
            Dimension
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="dimension"
              variant="outlined"
              label="Dimension"
              onChange={handleChange}
            />
          </Grid>

        </Grid>

        <Box mt={3}>
          <Button color="primary" variant="contained" type="submit">
            Submit
          </Button>
        </Box>
      </Form>
    </Card>
  );
}
