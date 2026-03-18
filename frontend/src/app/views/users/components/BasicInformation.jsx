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
import { People, AccountTree, Key, AccountBalanceWallet } from "@mui/icons-material";
import api from "app/utils/api";

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

    api.patch("/users/" + user.username, update, auth.user.token)
      .then(() => {
        window.location.href = "/admin/user/" + user.username;
      })
      .catch(() => {});
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

              {user.options?.credit >= 0 && (
                <FlexBox alignItems="center" gap={1}>
                  <AccountBalanceWallet sx={{ color: "text.disabled" }} />
                  <Small fontWeight={600} color="text.disabled">
                    Credit: {user.options.credit.toFixed(2)} | Spent: {(user.spending ?? 0).toFixed(2)} | Left: {(user.remaining ?? 0).toFixed(2)}
                  </Small>
                </FlexBox>
              )}
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
