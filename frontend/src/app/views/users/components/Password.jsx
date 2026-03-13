import { Box, Button, Card, Divider, Grid, Stack, styled, TextField } from "@mui/material";
import { useState } from "react";
import { FlexBox } from "app/components/FlexBox";
import { H5, Paragraph } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';

const Dot = styled("div")(({ theme }) => ({
  width: 8,
  height: 8,
  flexShrink: 0,
  borderRadius: "50%",
  backgroundColor: theme.palette.primary.main
}));

export default function Password({user}) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [state, setState] = useState({});

  const handleSubmit = (event) => {
    event.preventDefault();

    if (state.newPassword !== state.confirmNewPassword) {
      toast.error("Passwords do not match");
      return;
    }

    var update = {"password": state.newPassword};

    fetch(url + "/users/" + user.username, {
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
      window.location.href = "/admin/user/" + user.username;
    }).catch(err => {
      console.log(err.toString());
      toast.error("Error updating user");
    });
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
  };

  return (
    <Card>
      <H5 padding={3}>Password</H5>
      <Divider />

      <Box padding={3}>
        <Grid container spacing={5}>
          <Grid item sm={6} xs={12}>
            <form onSubmit={handleSubmit}>
              <Stack spacing={4}>
                <TextField
                  fullWidth
                  type="password"
                  name="newPassword"
                  variant="outlined"
                  label="New Password"
                  onChange={handleChange}
                  value={state.newPassword}
                />
                <TextField
                  fullWidth
                  type="password"
                  variant="outlined"
                  name="confirmNewPassword"
                  label="Confirm Password"
                  onChange={handleChange}
                  value={state.confirmNewPassword}
                />
              </Stack>

              <Stack direction="row" spacing={3} mt={4}>
                <Button type="submit" variant="contained">
                  Save Changes
                </Button>
              </Stack>
            </form>
          </Grid>

          <Grid item sm={6} xs={12}>
            <H5>Password recommendations:</H5>

            <Stack spacing={1} mt={2}>
              <FlexBox alignItems="center" gap={1}>
                <Dot />
                <Paragraph fontSize={13}>
                  8 characters long - the more, the better
                </Paragraph>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <Dot />
                <Paragraph fontSize={13}>At least one lowercase character</Paragraph>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <Dot />
                <Paragraph fontSize={13}>At least one uppercase character</Paragraph>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}> 
                <Dot />
                <Paragraph fontSize={13}>
                  At least one number, symbol, or whitespace character
                </Paragraph>
              </FlexBox>
            </Stack>
          </Grid>
        </Grid>
      </Box>
    </Card>
  );
}
