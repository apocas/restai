import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, Checkbox, Grid, TextField, Box, styled, Button } from "@mui/material";
import { LoadingButton } from "@mui/lab";
import GitHubIcon from '@mui/icons-material/GitHub';
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

export default function JwtLogin() {
  const [type, setType] = useState(null);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState({});
  const { platformCapabilities } = usePlatformCapabilities();
  const ssoProviders = platformCapabilities?.sso || [];

  const { login } = useAuth();

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (type === null) {
      setType("password");
    }
      
    if (type === "password") {
      try {
        await login(state.email, state.password);
        window.location.href = "/admin";
      } catch (e) {
        setLoading(false);
      }
    }
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: (event.target.type === "checkbox" ? event.target.checked : event.target.value) });
  };

  const handleGitHubLogin = async () => {
    window.location.href = "/oauth/github/login";
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

                  {ssoProviders.includes("github") && (
                    <Button
                      onClick={handleGitHubLogin}
                      type="button"
                      color="primary"
                      variant="contained"
                      sx={{ my: 2, ml: 0.2 }}>
                      Login with GitHub
                      <GitHubIcon sx={{ ml: 1 }} />
                    </Button>
                  )}

                </form>
              </Grid>
            </ContentBox>
          </Grid>
        </Grid>
      </Card>
    </StyledRoot>
  );
}
