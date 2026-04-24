import { Box, Button, Card, Divider, Grid, Stack, styled, TextField, Alert } from "@mui/material";
import { useState, useEffect } from "react";
import { FlexBox } from "app/components/FlexBox";
import { H5, Paragraph } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Dot = styled("div")(({ theme }) => ({
  width: 8,
  height: 8,
  flexShrink: 0,
  borderRadius: "50%",
  backgroundColor: theme.palette.primary.main
}));

export default function Password({user}) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [state, setState] = useState({});
  const [totpEnabled, setTotpEnabled] = useState(false);

  useEffect(() => {
    if (!user?.username) return;
    api.get(`/users/${user.username}/totp/status`, auth.user.token, { silent: true })
      .then((d) => { if (d) setTotpEnabled(d.enabled); })
      .catch(() => {});
  }, [user?.username]);

  const handleSubmit = (event) => {
    event.preventDefault();

    if (state.newPassword !== state.confirmNewPassword) {
      toast.error(t("users.password.mismatch"));
      return;
    }

    if (totpEnabled && !state.totpCode) {
      toast.error(t("users.password.twoFactorRequired"));
      return;
    }

    var update = {"password": state.newPassword};
    if (totpEnabled && state.totpCode) update.totp_code = state.totpCode;

    api.patch("/users/" + user.username, update, auth.user.token)
      .then(() => {
        window.location.href = "/admin/user/" + user.username;
      })
      .catch(() => {});
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
  };

  return (
    <Card>
      <H5 padding={3}>{t("users.password.title")}</H5>
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
                  label={t("users.password.newPassword")}
                  onChange={handleChange}
                  value={state.newPassword}
                />
                <TextField
                  fullWidth
                  type="password"
                  variant="outlined"
                  name="confirmNewPassword"
                  label={t("users.password.confirmPassword")}
                  onChange={handleChange}
                  value={state.confirmNewPassword}
                />
                {totpEnabled && (
                  <>
                    <Alert severity="info" sx={{ py: 0.5 }}>
                      {t("users.password.twoFactorAlert")}
                    </Alert>
                    <TextField
                      fullWidth
                      name="totpCode"
                      variant="outlined"
                      label={t("users.password.twoFactorCode")}
                      onChange={handleChange}
                      value={state.totpCode || ""}
                      inputProps={{ maxLength: 6, autoComplete: "one-time-code" }}
                    />
                  </>
                )}
              </Stack>

              <Stack direction="row" spacing={3} mt={4}>
                <Button type="submit" variant="contained">
                  {t("users.password.saveChanges")}
                </Button>
              </Stack>
            </form>
          </Grid>

          <Grid item sm={6} xs={12}>
            <H5>{t("users.password.recommendations")}</H5>

            <Stack spacing={1} mt={2}>
              <FlexBox alignItems="center" gap={1}>
                <Dot />
                <Paragraph fontSize={13}>
                  {t("users.password.recMin")}
                </Paragraph>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <Dot />
                <Paragraph fontSize={13}>{t("users.password.recLower")}</Paragraph>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <Dot />
                <Paragraph fontSize={13}>{t("users.password.recUpper")}</Paragraph>
              </FlexBox>

              <FlexBox alignItems="center" gap={1}>
                <Dot />
                <Paragraph fontSize={13}>
                  {t("users.password.recSymbol")}
                </Paragraph>
              </FlexBox>
            </Stack>
          </Grid>
        </Grid>
      </Box>
    </Card>
  );
}
