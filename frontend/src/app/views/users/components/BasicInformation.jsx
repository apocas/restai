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
  Typography,
  MenuItem
} from "@mui/material";
import AvatarBadge from "./AvatarBadge";
import { H4, H5, Small } from "app/components/Typography";
import { FlexBetween, FlexBox } from "app/components/FlexBox";
import sha256 from 'crypto-js/sha256';
import FormControlLabel from "@mui/material/FormControlLabel";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { People, AccountTree, Key, PersonOutline } from "@mui/icons-material";
import { SUPPORTED_LANGUAGES, applyLanguage } from "app/i18n";
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
  const { t, i18n: i18nInstance } = useTranslation();
  const auth = useAuth();
  const [state, setState] = useState({});
  const navigate = useNavigate();

  // Language is only editable when editing your own profile. Read the
  // current value from user.options.language if present, otherwise fall
  // back to i18n's active language so the dropdown shows something sane.
  const isSelf = auth.user?.username === user.username;
  const initialLang = (() => {
    try {
      const opts = typeof user.options === "string" ? JSON.parse(user.options) : user.options;
      return (opts && opts.language) || i18nInstance.language || "en";
    } catch {
      return i18nInstance.language || "en";
    }
  })();
  const [language, setLanguage] = useState(initialLang);

  useEffect(() => { setLanguage(initialLang); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [user]);

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
    if (state.is_restricted !== user.is_restricted) {
      update.is_restricted = state.is_restricted;
    }
    if (isSelf && language !== initialLang) {
      const prevOpts = (user.options && typeof user.options === "object") ? user.options : {};
      update.options = { ...prevOpts, language };
    }

    api.patch("/users/" + user.username, update, auth.user.token)
      .then(() => {
        if (isSelf && language !== initialLang) applyLanguage(language);
        window.location.href = "/admin/user/" + user.username;
      })
      .catch(() => {});
  }

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
  };

  useEffect(() => {
    setState({ ...user });
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
                  {user.projects && user.projects.length} {t("users.basic.projects")}
                </Small>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <People sx={{ color: "text.disabled" }} />
                <Small fontWeight={600} color="text.disabled">
                  {user.is_admin ? t("users.basic.roleAdmin") : t("users.basic.roleRegular")}
                </Small>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <Key sx={{ color: "text.disabled" }} />
                <Small fontWeight={600} color="text.disabled">
                  {user.sso ? t("users.basic.authSso") : t("users.basic.authLocal")}
                </Small>
              </FlexBox>

            </FlexBetween>

            {auth.user.is_admin && user.username !== auth.user.username && (
              <Box mt={2} textAlign="center">
                <Button
                  size="small"
                  variant="outlined"
                  color="warning"
                  startIcon={<PersonOutline />}
                  onClick={() => {
                    auth.impersonate(user.username);
                  }}
                >
                  {t("users.basic.impersonate")}
                </Button>
              </Box>
            )}

          </Box>
        </ContentWrapper>
      </Card>

      <Card sx={{ mt: 3 }}>
        <H5 padding={3}>{t("users.basic.title")}</H5>
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
                  label={t("users.fields.username")}
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
                  label={t("users.basic.authSso")}
                  variant="outlined"
                  onChange={handleChange}
                  value={user.sso ?? ''}
                />
              </Grid>

              {isSelf && (
                <Grid item sm={6} xs={12}>
                  <TextField
                    select
                    fullWidth
                    InputLabelProps={{ shrink: true }}
                    name="language"
                    label={t("users.basic.language")}
                    variant="outlined"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                    helperText={t("users.basic.languageHelp")}
                  >
                    {SUPPORTED_LANGUAGES.map((lang) => (
                      <MenuItem key={lang.code} value={lang.code}>
                        {lang.nativeLabel}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>
              )}

              {auth.user.is_admin === true &&
                <Grid item sm={6} xs={12}>
                  <FormControlLabel
                    label={t("users.fields.isAdmin")}
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
                      label={t("users.fields.isPrivate")}
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
                    <FormControlLabel
                      label={t("users.basic.restricted")}
                      control={
                        <Switch
                          checked={state.is_restricted ?? false}
                          name="is_restricted"
                          inputProps={{ "aria-label": "restricted checkbox" }}
                          onChange={handleChange}
                        />
                      }
                    />
                    <Typography variant="caption" color="text.secondary" display="block">
                      {t("users.basic.restrictedHelp")}
                    </Typography>
                  </Grid>
                </>
              )}


              <Grid item xs={12}>
                <Button type="submit" variant="contained">
                  {t("users.basic.saveChanges")}
                </Button>
                <Button variant="outlined" sx={{ ml: 2 }} onClick={() => { navigate("/users") }}>
                  {t("common.cancel")}
                </Button>
              </Grid>
            </Grid>
          </Box>
        </form>
      </Card>
    </Fragment>
  );
}
