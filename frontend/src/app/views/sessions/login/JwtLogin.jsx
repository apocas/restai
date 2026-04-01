import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Checkbox, Grid, TextField, Box, styled, Button, Typography } from "@mui/material";
import { LoadingButton } from "@mui/lab";
import GitHubIcon from '@mui/icons-material/GitHub';
import GoogleIcon from '@mui/icons-material/Google';
import VpnKeyIcon from '@mui/icons-material/VpnKey';
import LockIcon from '@mui/icons-material/Lock';
import useAuth from "app/hooks/useAuth";
import { Paragraph, Span } from "app/components/Typography";
import { toast } from 'react-toastify';
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

const FlexBox = styled(Box)(() => ({
  display: "flex"
}));

const ContentBox = styled("div")(() => ({
  height: "100%",
  padding: "32px",
  position: "relative",
}));

const StyledRoot = styled("div")(() => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: "#1A2038",
  minHeight: "100% !important",
  "& .card": {
    maxWidth: 800,
    minHeight: 400,
    margin: "1rem",
    display: "flex",
    borderRadius: 12,
    alignItems: "center"
  },

  ".img-wrapper": {
    height: "100%",
    minWidth: 320,
    display: "flex",
    padding: "2rem",
    alignItems: "center",
    justifyContent: "center"
  }
}));

const StyledSpan = styled(Span)(({ mode }) => ({
  fontSize: 18,
  display: mode === "compact" ? "none" : "block",
  marginBottom: "2rem"
}));

const SSO_ICON_MAP = {
  google: <GoogleIcon sx={{ ml: 1 }} />,
  github: <GitHubIcon sx={{ ml: 1 }} />,
  microsoft: <Box component="img" src="/admin/assets/images/microsoft-icon.svg" alt="Microsoft" sx={{ ml: 1, width: 20, height: 20 }} onError={(e) => { e.target.style.display = 'none'; }} />,
  oidc: <VpnKeyIcon sx={{ ml: 1 }} />,
};

export default function JwtLogin() {
  const [type, setType] = useState(null);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState({});
  const [totpToken, setTotpToken] = useState(null);
  const [totpCode, setTotpCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const { platformCapabilities } = usePlatformCapabilities();
  const ssoProviders = platformCapabilities?.sso || [];
  const ssoProviderNames = platformCapabilities?.sso_provider_names || {};
  const authDisableLocal = platformCapabilities?.auth_disable_local || false;

  const { login, verifyTotp } = useAuth();

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (type === null) {
      setType("password");
      return;
    }

    if (type === "password") {
      setLoading(true);
      try {
        const result = await login(state.email, state.password);
        if (result && result.requires_totp) {
          setTotpToken(result.totp_token);
          setType("totp");
          setLoading(false);
        } else {
          window.location.href = "/admin";
        }
      } catch (e) {
        toast.error(e.message);
        setLoading(false);
      }
    }
  };

  const handleTotpSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);
    try {
      await verifyTotp(totpToken, totpCode);
      window.location.href = "/admin";
    } catch (e) {
      toast.error(e.message);
      setLoading(false);
    }
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
  };

  const handleSSOLogin = (provider) => () => {
    window.location.href = `/oauth/${provider}/login`;
  };

  return (
    <StyledRoot>
      <Card className="card">
        <Grid container>
          <Grid item sm={6} xs={12}>
            <div className="img-wrapper">
              <img src="/admin/assets/images/restai-logo.png" width="80%" alt="" />
            </div>
          </Grid>

          <Grid item sm={6} xs={12}>
            <ContentBox>
              <Grid item sm={12} xs={12}>
                <StyledSpan className="sidenavHoverShow">
                  {process.env.REACT_APP_RESTAI_NAME || "RESTai"}
                </StyledSpan>
              </Grid>
              <Grid item sm={12} xs={12}>
                {/* TOTP verification step */}
                {type === "totp" ? (
                  <form onSubmit={handleTotpSubmit}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 2 }}>
                      <LockIcon color="primary" />
                      <Typography variant="subtitle1">Two-Factor Authentication</Typography>
                    </Box>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                      {useRecovery
                        ? "Enter one of your recovery codes."
                        : "Enter the 6-digit code from your authenticator app."}
                    </Typography>
                    <TextField
                      fullWidth
                      size="small"
                      autoFocus
                      label={useRecovery ? "Recovery Code" : "Authentication Code"}
                      value={totpCode}
                      onChange={(e) => setTotpCode(e.target.value)}
                      variant="outlined"
                      placeholder={useRecovery ? "abcd1234" : "123456"}
                      inputProps={{ maxLength: useRecovery ? 20 : 6, autoComplete: "one-time-code" }}
                      sx={{ mb: 1.5 }}
                    />
                    <Button
                      size="small"
                      onClick={() => { setUseRecovery(!useRecovery); setTotpCode(""); }}
                      sx={{ mb: 1, textTransform: "none" }}
                    >
                      {useRecovery ? "Use authenticator code" : "Use a recovery code"}
                    </Button>
                    <LoadingButton
                      type="submit"
                      color="primary"
                      loading={loading}
                      variant="contained"
                      fullWidth
                      sx={{ my: 1 }}
                    >
                      Verify
                    </LoadingButton>
                    <Button
                      size="small"
                      fullWidth
                      onClick={() => { setType(null); setTotpToken(null); setTotpCode(""); setLoading(false); }}
                      sx={{ textTransform: "none" }}
                    >
                      Back to login
                    </Button>
                  </form>
                ) : (
                  <>
                    {/* Normal login form */}
                    {!authDisableLocal && (
                      <form onSubmit={handleSubmit}>
                        <TextField
                          fullWidth
                          size="small"
                          type="text"
                          name="email"
                          label="Username/Email"
                          variant="outlined"
                          onChange={handleChange}
                          sx={{ mb: 3 }}
                        />

                        {type === "password" && (<TextField
                          fullWidth
                          size="small"
                          name="password"
                          type="password"
                          label="Password"
                          variant="outlined"
                          onChange={handleChange}
                          sx={{ mb: 1.5 }}
                        />)}

                        <FlexBox justifyContent="space-between">
                          <FlexBox gap={1}>
                            <Checkbox
                              size="small"
                              name="remember"
                              onChange={handleChange}
                              checked={state.remember}
                              sx={{ padding: 0 }}
                            />
                            <Paragraph>Remember Me</Paragraph>
                          </FlexBox>
                        </FlexBox>

                        <LoadingButton
                          type="submit"
                          color="primary"
                          loading={loading}
                          variant="contained"
                          sx={{ my: 2 }}>
                          Login
                        </LoadingButton>
                      </form>
                    )}

                    {ssoProviders.map((provider) => (
                      <Button
                        key={provider}
                        onClick={handleSSOLogin(provider)}
                        type="button"
                        color="primary"
                        variant="contained"
                        sx={{ my: 1, mr: 1 }}>
                        Login with {ssoProviderNames[provider] || provider.charAt(0).toUpperCase() + provider.slice(1)}
                        {SSO_ICON_MAP[provider] || <VpnKeyIcon sx={{ ml: 1 }} />}
                      </Button>
                    ))}
                  </>
                )}
              </Grid>
            </ContentBox>
          </Grid>
        </Grid>
      </Card>
    </StyledRoot>
  );
}
