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
  TextField
} from "@mui/material";

import { H4 } from "app/components/Typography";
import { toast } from 'react-toastify';

const Form = styled("form")(() => ({ padding: "16px" }));

export default function UserNew() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [state, setState] = useState({});

  const url = process.env.REACT_APP_RESTAI_API_URL || "";

  const handleSubmit = async (event) => {
    event.preventDefault();
    console.log(state);

    var opts = {
      "username": state.username,
      "password": state.password,
      "is_admin": false,
      "is_private": false
    }

    fetch(url + "/users", {
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
        navigate("/user/" + response.username);
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
      <H4 p={2}>Add a New User</H4>

      <Divider sx={{ mb: 1 }} />

      <Form onSubmit={handleSubmit}>
        <Grid container spacing={3} alignItems="center">
          <Grid item md={2} sm={4} xs={12}>
            Username
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="username"
              variant="outlined"
              label="Username"
              onChange={handleChange}
            />
          </Grid>

          <Grid item md={2} sm={4} xs={12}>
            Password
          </Grid>

          <Grid item md={10} sm={8} xs={12}>
            <TextField
              size="small"
              name="password"
              type="password"
              variant="outlined"
              label="Password"
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
