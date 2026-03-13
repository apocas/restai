import { Fragment, useState, useEffect } from "react";
import {
  Box,
  Card,
  Grid,
  Button,
  styled,
  Divider,
  TextField,
  Switch
} from "@mui/material";
import AvatarBadge from "./AvatarBadge";
import { H4, H5, Small } from "app/components/Typography";
import { FlexBetween, FlexBox } from "app/components/FlexBox";
import sha256 from 'crypto-js/sha256';
import FormControlLabel from "@mui/material/FormControlLabel";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { toast } from 'react-toastify';
import { People, AccountTree, Key } from "@mui/icons-material";

const ContentWrapper = styled(Box)(({ theme }) => ({
  zIndex: 1,
  position: "relative",
  [theme.breakpoints.down("sm")]: { paddingLeft: 20, paddingRight: 20 }
}));

const ImageWrapper = styled(Box)(({ theme }) => ({
  margin: "auto",
  borderRadius: "50%",
  border: "2px solid",
  borderColor: "white",
  backgroundColor: theme.palette.primary[200]
}));

export default function BasicInformation({ user }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [state, setState] = useState({});
  const navigate = useNavigate();

  const handleSubmit = (event) => {
    event.preventDefault();

    var update = {};

    if (state.is_admin !== user.is_admin) {
      update.is_admin = state.is_admin;
    }
    if (state.sso !== user.sso) {
      update.sso = state.sso;
    }
    if (state.is_private !== user.is_private) {
      update.is_private = state.is_private;
    }

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
  }

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
  };

  useEffect(() => {
    setState(user);
  }, [user]);

  return (
    <Fragment>
      <Card sx={{ padding: 3, position: "relative" }}>


        <ContentWrapper>
          <FlexBox justifyContent="center">
            <AvatarBadge>
              <ImageWrapper>
                <img src={`https://www.gravatar.com/avatar/${sha256(user.username).toString()}`} alt="Gravatar" sizes="large" style={{ borderRadius: "50%" }} />
              </ImageWrapper>
            </AvatarBadge>
          </FlexBox>

          <Box mt={0}>
            <H4 fontWeight={600} textAlign="center">
              {user.username}
            </H4>

            <FlexBetween maxWidth={400} flexWrap="wrap" margin="auto" mt={1}>
              <FlexBox alignItems="center" gap={1}>
                <AccountTree sx={{ color: "text.disabled" }} />
                <Small fontWeight={600} color="text.disabled">
                  {user.projects && user.projects.length} Projects
                </Small>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <People sx={{ color: "text.disabled" }} />
                <Small fontWeight={600} color="text.disabled">
                  {user.is_admin ? "Admin" : "Regular"}
                </Small>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <Key sx={{ color: "text.disabled" }} />
                <Small fontWeight={600} color="text.disabled">
                  {user.sso ? "SSO" : "Local"}
                </Small>
              </FlexBox>
            </FlexBetween>
          </Box>
        </ContentWrapper>
      </Card>

      <Card sx={{ mt: 3 }}>
        <H5 padding={3}>Basic Information</H5>
        <Divider />

        <form onSubmit={handleSubmit}>
          <Box margin={3}>
            <Grid container spacing={3}>
              <Grid item sm={6} xs={12}>
                <TextField
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  disabled
                  name="username"
                  label="Username"
                  variant="outlined"
                  onChange={handleChange}
                  value={user.username ?? ''}
                />
              </Grid>

              <Grid item sm={6} xs={12}>
                <TextField
                  fullWidth
                  InputLabelProps={{ shrink: true }}
                  name="sso"
                  label="SSO"
                  variant="outlined"
                  onChange={handleChange}
                  value={user.sso ?? ''}
                />
              </Grid>

              {auth.user.is_admin === true &&
                <>
                  <Grid item sm={6} xs={12}>
                    <FormControlLabel
                      label="Administrator"
                      control={
                        <Switch
                          checked={state.is_admin ?? false}
                          name="is_admin"
                          inputProps={{ "aria-label": "secondary checkbox controlled" }}
                          onChange={handleChange}
                        />
                      }
                    />
                  </Grid>

                  <Grid item sm={6} xs={12}>
                    <FormControlLabel
                      label="Local AI only"
                      control={
                        <Switch
                          checked={state.is_private ?? false}
                          name="is_private"
                          inputProps={{ "aria-label": "secondary checkbox controlled" }}
                          onChange={handleChange}
                        />
                      }
                    />
                  </Grid>
                </>
              }


              <Grid item xs={12}>
                <Button type="submit" variant="contained">
                  Save Changes
                </Button>
                <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/users") }}>
                  Cancel
                </Button>
              </Grid>
            </Grid>
          </Box>
        </form>
      </Card>
    </Fragment>
  );
}
