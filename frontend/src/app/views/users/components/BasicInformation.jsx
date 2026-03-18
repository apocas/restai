import { Fragment, useState, useEffect } from "react";
import {
  Box,
  Card,
  Grid,
  Button,
  styled,
  Divider,
  TextField,
  Switch,
  LinearProgress,
  Typography
} from "@mui/material";
import AvatarBadge from "./AvatarBadge";
import { H4, H5, Small } from "app/components/Typography";
import { FlexBetween, FlexBox } from "app/components/FlexBox";
import sha256 from 'crypto-js/sha256';
import FormControlLabel from "@mui/material/FormControlLabel";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { People, AccountTree, Key, AccountBalanceWallet, AllInclusive } from "@mui/icons-material";
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

    const newCredit = parseFloat(state.credit);
    const oldCredit = user.options?.credit ?? -1.0;
    if (!isNaN(newCredit) && newCredit !== oldCredit) {
      update.options = { credit: newCredit };
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
    setState({ ...user, credit: user.options?.credit ?? -1.0 });
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

            {user.options?.credit >= 0 ? (() => {
              const spent = user.spending ?? 0;
              const credit = user.options.credit;
              const pct = credit > 0 ? Math.min((spent / credit) * 100, 100) : 0;
              const barColor = pct > 90 ? "error" : pct > 70 ? "warning" : "primary";
              return (
                <Box maxWidth={400} margin="auto" mt={2}>
                  <FlexBetween mb={0.5}>
                    <FlexBox alignItems="center" gap={0.5}>
                      <AccountBalanceWallet sx={{ fontSize: 16, color: "text.secondary" }} />
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        Spent (this month): ${spent.toFixed(2)} / ${credit.toFixed(2)}
                      </Typography>
                    </FlexBox>
                    <Typography variant="caption" color="text.secondary" fontWeight={600}>
                      ${(user.remaining ?? 0).toFixed(2)} left
                    </Typography>
                  </FlexBetween>
                  <LinearProgress
                    variant="determinate"
                    value={pct}
                    color={barColor}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                </Box>
              );
            })() : (
              <Box maxWidth={400} margin="auto" mt={2}>
                <FlexBox alignItems="center" justifyContent="center" gap={0.5}>
                  <AllInclusive sx={{ fontSize: 16, color: "text.disabled" }} />
                  <Typography variant="caption" color="text.disabled" fontWeight={600}>
                    Unlimited
                  </Typography>
                </FlexBox>
              </Box>
            )}
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
              }

              {(auth.user.is_admin || auth.user.admin_teams?.length > 0) && (
                <>
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

                  <Grid item sm={6} xs={12}>
                    <TextField
                      fullWidth
                      InputLabelProps={{ shrink: true }}
                      name="credit"
                      label="Credit Balance (-1 = unlimited)"
                      variant="outlined"
                      type="number"
                      inputProps={{ step: "0.01" }}
                      onChange={handleChange}
                      value={state.credit ?? -1.0}
                      helperText="Set the user's spending credit limit. -1 means no limit."
                    />
                  </Grid>
                </>
              )}


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
