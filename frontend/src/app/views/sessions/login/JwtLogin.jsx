import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, TextField, Button, Typography, Alert, Collapse,
  Checkbox, FormControlLabel, Divider, styled, keyframes,
} from "@mui/material";
import { LoadingButton } from "@mui/lab";
import GitHubIcon from "@mui/icons-material/GitHub";
import GoogleIcon from "@mui/icons-material/Google";
import VpnKeyIcon from "@mui/icons-material/VpnKey";
import LockIcon from "@mui/icons-material/Lock";
import useAuth from "app/hooks/useAuth";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

// --- Animations ---
const gradientShift = keyframes`
  0% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
  100% { background-position: 0% 50%; }
`;

const float1 = keyframes`
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -20px) scale(1.05); }
  66% { transform: translate(-20px, 15px) scale(0.95); }
`;

const float2 = keyframes`
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-25px, 20px) scale(0.95); }
  66% { transform: translate(15px, -25px) scale(1.08); }
`;

const fadeSlideUp = keyframes`
  from { opacity: 0; transform: translateY(20px); }
  to { opacity: 1; transform: translateY(0); }
`;

const shake = keyframes`
  0%, 100% { transform: translateX(0); }
  15% { transform: translateX(-8px); }
  30% { transform: translateX(6px); }
  45% { transform: translateX(-4px); }
  60% { transform: translateX(2px); }
`;

// --- Styled Components ---
const Root = styled("div")({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  position: "relative",
  overflow: "hidden",
  background: "linear-gradient(135deg, #0a0a1a 0%, #0d1129 25%, #111833 50%, #0a1628 75%, #080e1f 100%)",
  backgroundSize: "400% 400%",
  animation: `${gradientShift} 15s ease infinite`,
});

const Orb = styled("div")(({ color, size, top, left, delay }) => ({
  position: "absolute",
  width: size || 400,
  height: size || 400,
  borderRadius: "50%",
  background: color || "rgba(99, 102, 241, 0.08)",
  filter: "blur(80px)",
  top: top || "20%",
  left: left || "10%",
  animation: `${delay ? float2 : float1} ${delay ? "12s" : "10s"} ease-in-out infinite`,
  pointerEvents: "none",
}));

const GlassCard = styled(Box)(({ shaking }) => ({
  position: "relative",
  zIndex: 2,
  width: "100%",
  maxWidth: 420,
  margin: "1rem",
  padding: "2.5rem 2rem 2rem",
  borderRadius: 20,
  background: "rgba(255, 255, 255, 0.04)",
  backdropFilter: "blur(24px) saturate(1.4)",
  border: "1px solid rgba(255, 255, 255, 0.08)",
  boxShadow: "0 24px 80px rgba(0, 0, 0, 0.4), 0 0 40px rgba(99, 102, 241, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.05)",
  animation: shaking
    ? `${shake} 0.4s ease, ${fadeSlideUp} 0.6s ease`
    : `${fadeSlideUp} 0.6s ease`,
  color: "#e2e8f0",
}));

const StyledInput = styled(TextField)({
  "& .MuiOutlinedInput-root": {
    borderRadius: 12,
    backgroundColor: "rgba(255, 255, 255, 0.04)",
    color: "#e2e8f0",
    fontSize: "0.95rem",
    transition: "all 0.2s ease",
    "& fieldset": {
      borderColor: "rgba(255, 255, 255, 0.1)",
      transition: "border-color 0.2s ease",
    },
    "&:hover fieldset": {
      borderColor: "rgba(99, 102, 241, 0.4)",
    },
    "&.Mui-focused fieldset": {
      borderColor: "#6366f1",
      boxShadow: "0 0 0 3px rgba(99, 102, 241, 0.12)",
    },
  },
  "& .MuiInputLabel-root": {
    color: "rgba(255, 255, 255, 0.45)",
    "&.Mui-focused": { color: "#818cf8" },
  },
});

const PrimaryButton = styled(LoadingButton)({
  borderRadius: 12,
  padding: "12px 0",
  fontSize: "0.95rem",
  fontWeight: 600,
  textTransform: "none",
  letterSpacing: "0.02em",
  background: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)",
  boxShadow: "0 4px 16px rgba(99, 102, 241, 0.3)",
  transition: "all 0.2s ease",
  "&:hover": {
    boxShadow: "0 6px 24px rgba(99, 102, 241, 0.45)",
    transform: "translateY(-1px)",
  },
  "&.Mui-disabled": {
    background: "rgba(99, 102, 241, 0.3)",
  },
});

const SSOButton = styled(Button)({
  borderRadius: 12,
  padding: "10px 16px",
  fontSize: "0.88rem",
  fontWeight: 500,
  textTransform: "none",
  color: "#c7d2fe",
  borderColor: "rgba(255, 255, 255, 0.1)",
  backgroundColor: "rgba(255, 255, 255, 0.03)",
  transition: "all 0.2s ease",
  "&:hover": {
    borderColor: "rgba(99, 102, 241, 0.5)",
    backgroundColor: "rgba(99, 102, 241, 0.08)",
  },
});

const OrDivider = styled(Box)({
  display: "flex",
  alignItems: "center",
  gap: 12,
  margin: "20px 0",
  "&::before, &::after": {
    content: '""',
    flex: 1,
    height: 1,
    background: "rgba(255, 255, 255, 0.08)",
  },
});

const SSO_ICON_MAP = {
  google: <GoogleIcon sx={{ fontSize: 18 }} />,
  github: <GitHubIcon sx={{ fontSize: 18 }} />,
  microsoft: (
    <Box
      component="img"
      src="/admin/assets/images/microsoft-icon.svg"
      alt=""
      sx={{ width: 18, height: 18, filter: "brightness(1.5)" }}
      onError={(e) => { e.target.style.display = "none"; }}
    />
  ),
  oidc: <VpnKeyIcon sx={{ fontSize: 18 }} />,
};

export default function JwtLogin() {
  const [type, setType] = useState(null);
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState({});
  const [error, setError] = useState("");
  const [shaking, setShaking] = useState(false);
  const [totpToken, setTotpToken] = useState(null);
  const [totpCode, setTotpCode] = useState("");
  const [useRecovery, setUseRecovery] = useState(false);
  const { platformCapabilities } = usePlatformCapabilities();
  const ssoProviders = platformCapabilities?.sso || [];
  const ssoProviderNames = platformCapabilities?.sso_provider_names || {};
  const authDisableLocal = platformCapabilities?.auth_disable_local || false;

  const { login, verifyTotp } = useAuth();

  const triggerError = (msg) => {
    setError(msg);
    setShaking(true);
    setTimeout(() => setShaking(false), 500);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
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
        triggerError(e.message || "Login failed. Please check your credentials.");
        setLoading(false);
      }
    }
  };

  const handleTotpSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      await verifyTotp(totpToken, totpCode);
      window.location.href = "/admin";
    } catch (e) {
      triggerError(e.message || "Invalid code.");
      setLoading(false);
    }
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setError("");
    setState({
      ...state,
      [event.target.name]: event.target.type === "checkbox" ? event.target.checked : event.target.value,
    });
  };

  const handleSSOLogin = (provider) => () => {
    window.location.href = `/oauth/${provider}/login`;
  };

  const appName = platformCapabilities?.app_name || process.env.REACT_APP_RESTAI_NAME || "RESTai";

  return (
    <Root>
      {/* Background orbs */}
      <Orb color="rgba(99, 102, 241, 0.07)" size={500} top="-10%" left="-5%" />
      <Orb color="rgba(139, 92, 246, 0.05)" size={400} top="60%" left="70%" delay />
      <Orb color="rgba(6, 182, 212, 0.04)" size={350} top="30%" left="50%" />

      <GlassCard shaking={shaking}>
        {/* Logo + App Name */}
        <Box sx={{ textAlign: "center", mb: 3.5 }}>
          <Box
            component="img"
            src="/admin/assets/images/restai-logo.png"
            alt={appName}
            sx={{
              width: 56,
              height: 56,
              mb: 1.5,
              filter: "drop-shadow(0 4px 12px rgba(99, 102, 241, 0.3))",
            }}
          />
          <Typography
            sx={{
              fontSize: "1.5rem",
              fontWeight: 700,
              letterSpacing: "-0.02em",
              background: "linear-gradient(135deg, #fff 30%, #818cf8)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            {appName}
          </Typography>
        </Box>

        {/* Error Alert */}
        <Collapse in={!!error}>
          <Alert
            severity="error"
            onClose={() => setError("")}
            sx={{
              mb: 2,
              borderRadius: 3,
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.2)",
              color: "#fca5a5",
              "& .MuiAlert-icon": { color: "#f87171" },
              "& .MuiAlert-action .MuiIconButton-root": { color: "#fca5a5" },
            }}
          >
            {error}
          </Alert>
        </Collapse>

        {/* TOTP Step */}
        {type === "totp" ? (
          <form onSubmit={handleTotpSubmit}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
              <LockIcon sx={{ color: "#818cf8", fontSize: 20 }} />
              <Typography sx={{ fontWeight: 600, fontSize: "1rem" }}>
                Two-Factor Authentication
              </Typography>
            </Box>
            <Typography sx={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.5)", mb: 2.5 }}>
              {useRecovery
                ? "Enter one of your recovery codes."
                : "Enter the 6-digit code from your authenticator app."}
            </Typography>
            <StyledInput
              fullWidth
              autoFocus
              label={useRecovery ? "Recovery Code" : "Authentication Code"}
              value={totpCode}
              onChange={(e) => { setTotpCode(e.target.value); setError(""); }}
              placeholder={useRecovery ? "abcd1234" : "123456"}
              inputProps={{ maxLength: useRecovery ? 20 : 6, autoComplete: "one-time-code" }}
              sx={{ mb: 1.5 }}
            />
            <Button
              size="small"
              onClick={() => { setUseRecovery(!useRecovery); setTotpCode(""); }}
              sx={{ mb: 2, textTransform: "none", color: "#818cf8", fontSize: "0.8rem" }}
            >
              {useRecovery ? "Use authenticator code" : "Use a recovery code"}
            </Button>
            <PrimaryButton type="submit" loading={loading} variant="contained" fullWidth>
              Verify
            </PrimaryButton>
            <Button
              fullWidth
              size="small"
              onClick={() => { setType(null); setTotpToken(null); setTotpCode(""); setLoading(false); setError(""); }}
              sx={{ mt: 1.5, textTransform: "none", color: "rgba(255,255,255,0.4)", fontSize: "0.8rem" }}
            >
              Back to login
            </Button>
          </form>
        ) : (
          <>
            {/* Local Login Form */}
            {!authDisableLocal && (
              <form onSubmit={handleSubmit}>
                <StyledInput
                  fullWidth
                  autoFocus
                  name="email"
                  label="Username or Email"
                  onChange={handleChange}
                  sx={{ mb: 2 }}
                />

                <Collapse in={type === "password"}>
                  <StyledInput
                    fullWidth
                    name="password"
                    type="password"
                    label="Password"
                    onChange={handleChange}
                    sx={{ mb: 2 }}
                  />
                </Collapse>

                <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2.5 }}>
                  <FormControlLabel
                    control={
                      <Checkbox
                        size="small"
                        name="remember"
                        onChange={handleChange}
                        checked={state.remember || false}
                        sx={{
                          color: "rgba(255,255,255,0.2)",
                          "&.Mui-checked": { color: "#818cf8" },
                        }}
                      />
                    }
                    label={
                      <Typography sx={{ fontSize: "0.82rem", color: "rgba(255,255,255,0.45)" }}>
                        Remember me
                      </Typography>
                    }
                  />
                </Box>

                <PrimaryButton type="submit" loading={loading} variant="contained" fullWidth>
                  {type === null ? "Continue" : "Sign In"}
                </PrimaryButton>
              </form>
            )}

            {/* SSO Section */}
            {ssoProviders.length > 0 && (
              <>
                {!authDisableLocal && (
                  <OrDivider>
                    <Typography sx={{ fontSize: "0.75rem", color: "rgba(255,255,255,0.25)", letterSpacing: "0.1em", textTransform: "uppercase" }}>
                      or
                    </Typography>
                  </OrDivider>
                )}

                <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  {ssoProviders.map((provider) => (
                    <SSOButton
                      key={provider}
                      variant="outlined"
                      fullWidth
                      onClick={handleSSOLogin(provider)}
                      startIcon={SSO_ICON_MAP[provider] || <VpnKeyIcon sx={{ fontSize: 18 }} />}
                    >
                      Continue with {ssoProviderNames[provider] || provider.charAt(0).toUpperCase() + provider.slice(1)}
                    </SSOButton>
                  ))}
                </Box>
              </>
            )}
          </>
        )}
      </GlassCard>
    </Root>
  );
}
