import { Card, Divider, Box, Grid, TextField, Button, Typography } from "@mui/material";
import { H4 } from "app/components/Typography";
import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import { useNavigate } from "react-router-dom";
import { JsonEditor } from 'json-edit-react';

export default function LLMEdit({ llm }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [state, setState] = useState({});
  const navigate = useNavigate();

  const handleSubmit = (event) => {
    event.preventDefault();

    var update = {};

    if (state.name !== llm.name) {
      update.name = state.name;
    }
    if (state.class_name !== llm.class_name) {
      update.class_name = state.class_name;
    }
    if (state.options !== llm.options) {
      update.options = state.options;
    }
    if (state.privacy !== llm.privacy) {
      update.privacy = state.privacy;
    }
    if (state.description !== llm.description) {
      update.description = state.description;
    }
    if (state.type !== llm.type) {
      update.type = state.type;
    }
    if (state.input_cost !== llm.input_cost) {
      update.input_cost = state.input_cost;
    }
    if (state.output_cost !== llm.output_cost) {
      update.output_cost = state.output_cost;
    }

    fetch(url + "/llms/" + llm.name, {
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
      window.location.href = "/admin/llm/" + llm.name;
    }).catch(err => {
      console.log(err.toString());
      toast.error("Error updating LLM");
    });
  }


  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  useEffect(() => {
    //llm.options = JSON.parse(llm.options || "{}");
    setState(llm);
  }, [llm]);

  return (
    <Card elevation={3}>
      <H4 p={2}>Edit LLM - {llm.name}</H4>

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
              <Typography variant="h6">Options</Typography>
              <JsonEditor
                data={state.options || {}}
                setData={(updatedOptions) => setState({ ...state, options: updatedOptions })}
                restrictDelete={false}
                rootName="Options"
                numberType="float"
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
                name="type"
                label="Type"
                variant="outlined"
                onChange={handleChange}
                value={state.type}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="input_cost"
                label="Input Cost"
                variant="outlined"
                onChange={handleChange}
                value={state.input_cost}
              />
            </Grid>

            <Grid item sm={6} xs={12}>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="output_cost"
                label="Output Cost"
                variant="outlined"
                onChange={handleChange}
                value={state.output_cost}
              />
            </Grid>

            <Grid item xs={12}>
              <Button type="submit" variant="contained">
                Save Changes
              </Button>
              <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/llms") }}>
                Cancel
              </Button>
            </Grid>
          </Grid>
        </Box>
      </form>
    </Card>
  );
}
