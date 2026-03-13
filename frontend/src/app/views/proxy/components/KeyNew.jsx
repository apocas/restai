import { useState } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  Divider,
  Grid,
  styled,
  TextField,
  Autocomplete
} from "@mui/material";

import { H4 } from "app/components/Typography";
import { toast } from 'react-toastify';
import ReactJson from '@microlink/react-json-view';

const Form = styled("form")(() => ({ padding: "16px" }));

export default function KeyNew({ info }) {
  const auth = useAuth();
  const navigate = useNavigate();



  const [state, setState] = useState({});

  const url = process.env.REACT_APP_RESTAI_API_URL || "";

  const handleSubmit = async (event) => {
    event.preventDefault();
    var opts = {
      "name": state.name,
      "models": state.models
    }

    fetch(url + "/proxy/keys", {
      method: 'POST',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      body: JSON.stringify(opts),
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((response) => {
        toast.success("Key created successfully");
        alert(response.key);
        navigate("/proxy/keys");
      }).catch(err => {
        toast.error(err.toString());
      });

  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  return (
    <Card elevation={3}>
      <H4 p={2}>Add a New Key</H4>

      <Divider sx={{ mb: 1 }} />

      <Grid container spacing={2}>

        <Grid item xs={8}>
          <Form onSubmit={handleSubmit}>
            <Grid container spacing={3} alignItems="center">
              <Grid item md={2} sm={4} xs={12}>
                Name
              </Grid>

              <Grid item md={10} sm={4} xs={12}>
                <TextField
                  size="small"
                  name="name"
                  variant="outlined"
                  label="Key Name"
                  fullWidth
                  sx={{ maxWidth: 500 }}
                  onChange={handleChange}
                />
              </Grid>

              <Grid item md={2} sm={4} xs={12}>
                Models
              </Grid>
              <Grid item sm={6} xs={12}>
                    <Autocomplete
                      multiple
                      id="tags-standard"
                      name="Models"
                      fullWidth
                      options={info.models.map((model) => model)}
                      getOptionLabel={(option) => option}
                      onChange={(event, newValue) => {
                        setState({ ...state, "models": newValue });
                      }}
                      defaultValue={state.models ? state.models : []}
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          fullWidth
                          variant="standard"
                          label=""
                          placeholder=""
                        />
                      )}
                    />
              </Grid>

            </Grid>
            <Box mt={3}>
              <Button color="primary" variant="contained" type="submit">
                Create
              </Button>
            </Box>
          </Form>
        </Grid>
        <Grid item xs={6}>
          {state.projectllm && (
            <ReactJson src={info.llms.find(llm => llm.name === state.projectllm)} enableClipboard={false} name={false} />
          )}
          {state.projectembeddings && (
            <ReactJson src={info.embeddings.find(embedding => embedding.name === state.projectembeddings)} enableClipboard={false} name={false} />
          )}
        </Grid>
      </Grid>
    </Card>
  );
}
