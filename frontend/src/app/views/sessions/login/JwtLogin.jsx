import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Box, TextField, Button, Typography, Alert, Collapse,
  Checkbox, FormControlLabel, styled, keyframes,
} from "@mui/material";
import { LoadingButton } from "@mui/lab";
import GitHubIcon from "@mui/icons-material/GitHub";
import GoogleIcon from "@mui/icons-material/Google";
import VpnKeyIcon from "@mui/icons-material/VpnKey";
import LockIcon from "@mui/icons-material/Lock";
import useAuth from "app/hooks/useAuth";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";

// --- Animations ---
const aurora = keyframes`
  0% { background-position: 0% 50%; transform: rotate(0deg); }
  25% { background-position: 50% 100%; }
  50% { background-position: 100% 50%; transform: rotate(1deg); }
  75% { background-position: 50% 0%; }
  100% { background-position: 0% 50%; transform: rotate(0deg); }
`;

const float1 = keyframes`
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.7; }
  25% { transform: translate(40px, -30px) scale(1.1); opacity: 0.9; }
  50% { transform: translate(-10px, 20px) scale(0.95); opacity: 0.6; }
  75% { transform: translate(20px, -10px) scale(1.05); opacity: 0.8; }
`;

const float2 = keyframes`
  0%, 100% { transform: translate(0, 0) scale(1); opacity: 0.6; }
  30% { transform: translate(-30px, 25px) scale(0.9); opacity: 0.8; }
  60% { transform: translate(25px, -35px) scale(1.12); opacity: 0.5; }
`;

const float3 = keyframes`
  0%, 100% { transform: translate(0, 0) scale(1) rotate(0deg); opacity: 0.5; }
  40% { transform: translate(15px, 30px) scale(1.08) rotate(2deg); opacity: 0.7; }
  80% { transform: translate(-20px, -15px) scale(0.92) rotate(-1deg); opacity: 0.4; }
`;

const fadeSlideUp = keyframes`
  from { opacity: 0; transform: translateY(24px) scale(0.97); }
  to { opacity: 1; transform: translateY(0) scale(1); }
`;

const logoPulse = keyframes`
  0%, 100% { filter: drop-shadow(0 0 20px rgba(56, 139, 253, 0.2)) drop-shadow(0 8px 24px rgba(0,0,0,0.3)); }
  50% { filter: drop-shadow(0 0 40px rgba(56, 139, 253, 0.35)) drop-shadow(0 8px 24px rgba(0,0,0,0.3)); }
`;

const shimmer = keyframes`
  0% { background-position: -200% center; }
  100% { background-position: 200% center; }
`;

const shake = keyframes`
  0%, 100% { transform: translateX(0); }
  15% { transform: translateX(-8px) rotate(-0.5deg); }
  30% { transform: translateX(6px) rotate(0.3deg); }
  45% { transform: translateX(-4px) rotate(-0.2deg); }
  60% { transform: translateX(2px); }
`;

const lineGlow = keyframes`
  0% { opacity: 0; width: 0; }
  50% { opacity: 1; width: 60px; }
  100% { opacity: 0; width: 0; }
`;

// --- Styled Components ---
const Root = styled("div")({
  minHeight: "100vh",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  position: "relative",
  overflow: "hidden",
  background: "#060613",
  "&::before": {
    content: '""',
    position: "absolute",
    inset: 0,
    background: "radial-gradient(ellipse 120% 80% at 50% 120%, rgba(56, 139, 253, 0.08) 0%, transparent 60%), radial-gradient(ellipse 100% 60% at 20% 0%, rgba(6, 182, 212, 0.05) 0%, transparent 50%), radial-gradient(ellipse 80% 60% at 80% 20%, rgba(30, 100, 200, 0.06) 0%, transparent 50%)",
    pointerEvents: "none",
  },
});

const GridOverlay = styled("div")({
  position: "absolute",
  inset: 0,
  backgroundImage: `linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px)`,
  backgroundSize: "60px 60px",
  maskImage: "radial-gradient(ellipse 70% 70% at 50% 50%, black 20%, transparent 70%)",
  pointerEvents: "none",
});

const Orb = styled("div")(({ color, size, top, left, anim }) => ({
  position: "absolute",
  width: size || 400,
  height: size || 400,
  borderRadius: "50%",
  background: color || "rgba(56, 139, 253, 0.08)",
  filter: "blur(100px)",
  top: top || "20%",
  left: left || "10%",
  animation: `${anim === 3 ? float3 : anim === 2 ? float2 : float1} ${anim === 3 ? "18s" : anim === 2 ? "14s" : "11s"} ease-in-out infinite`,
  pointerEvents: "none",
}));

const GlassCard = styled(Box)(({ shaking }) => ({
  position: "relative",
  zIndex: 2,
  width: "100%",
  maxWidth: 440,
  margin: "1rem",
  padding: "3rem 2.5rem 2.5rem",
  borderRadius: 24,
  background: "linear-gradient(145deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)",
  backdropFilter: "blur(40px) saturate(1.5)",
  border: "1px solid rgba(255, 255, 255, 0.07)",
  boxShadow: `
    0 32px 100px rgba(0, 0, 0, 0.5),
    0 0 60px rgba(56, 139, 253, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.06),
    inset 0 -1px 0 rgba(0, 0, 0, 0.1)
  `,
  animation: shaking
    ? `${shake} 0.4s ease`
    : `${fadeSlideUp} 0.7s cubic-bezier(0.16, 1, 0.3, 1)`,
  color: "#e2e8f0",
  "&::before": {
    content: '""',
    position: "absolute",
    top: 0,
    left: "50%",
    transform: "translateX(-50%)",
    width: 80,
    height: 2,
    borderRadius: 2,
    background: "linear-gradient(90deg, transparent, rgba(56, 139, 253, 0.6), transparent)",
    animation: `${lineGlow} 3s ease-in-out infinite`,
  },
}));

const StyledInput = styled(TextField)({
  "& .MuiOutlinedInput-root": {
    borderRadius: 14,
    backgroundColor: "rgba(255, 255, 255, 0.03)",
    color: "#e2e8f0",
    fontSize: "0.95rem",
    transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
    "& fieldset": {
      borderColor: "rgba(255, 255, 255, 0.08)",
      transition: "all 0.3s ease",
    },
    "&:hover fieldset": {
      borderColor: "rgba(56, 139, 253, 0.35)",
    },
    "&.Mui-focused": {
      backgroundColor: "rgba(56, 139, 253, 0.04)",
    },
    "&.Mui-focused fieldset": {
      borderColor: "#388bfd",
      boxShadow: "0 0 0 4px rgba(56, 139, 253, 0.1), 0 0 20px rgba(56, 139, 253, 0.05)",
    },
  },
  "& .MuiInputLabel-root": {
    color: "rgba(255, 255, 255, 0.35)",
    "&.Mui-focused": { color: "#79c0ff" },
  },
});

const PrimaryButton = styled(LoadingButton)({
  borderRadius: 14,
  padding: "13px 0",
  fontSize: "0.95rem",
  fontWeight: 600,
  textTransform: "none",
  letterSpacing: "0.02em",
  background: "linear-gradient(135deg, #388bfd 0%, #58a6ff 50%, #388bfd 100%)",
  backgroundSize: "200% auto",
  boxShadow: "0 4px 20px rgba(56, 139, 253, 0.25), inset 0 1px 0 rgba(255,255,255,0.15)",
  transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
  "&:hover": {
    backgroundPosition: "right center",
    boxShadow: "0 8px 32px rgba(56, 139, 253, 0.4), inset 0 1px 0 rgba(255,255,255,0.15)",
    transform: "translateY(-1px)",
  },
  "&:active": {
    transform: "translateY(0)",
  },
  "&.Mui-disabled": {
    background: "rgba(56, 139, 253, 0.2)",
    boxShadow: "none",
  },
});

const SSOButton = styled(Button)({
  borderRadius: 14,
  padding: "11px 16px",
  fontSize: "0.88rem",
  fontWeight: 500,
  textTransform: "none",
  color: "rgba(255,255,255,0.7)",
  borderColor: "rgba(255, 255, 255, 0.07)",
  backgroundColor: "rgba(255, 255, 255, 0.02)",
  backdropFilter: "blur(8px)",
  transition: "all 0.25s ease",
  "&:hover": {
    borderColor: "rgba(56, 139, 253, 0.4)",
    backgroundColor: "rgba(56, 139, 253, 0.06)",
    color: "#a5d6ff",
    transform: "translateY(-1px)",
    boxShadow: "0 4px 12px rgba(0,0,0,0.2)",
  },
});

const OrDivider = styled(Box)({
  display: "flex",
  alignItems: "center",
  gap: 16,
  margin: "24px 0",
  "&::before, &::after": {
    content: '""',
    flex: 1,
    height: 1,
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.06), transparent)",
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
    if (type === null) { setType("password"); return; }
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
    setState({ ...state, [event.target.name]: event.target.type === "checkbox" ? event.target.checked : event.target.value });
  };

  const handleSSOLogin = (provider) => () => {
    window.location.href = `/oauth/${provider}/login`;
  };

  const appName = platformCapabilities?.app_name || process.env.REACT_APP_RESTAI_NAME || "RESTai";

  return (
    <Root>
      {/* Subtle grid overlay */}
      <GridOverlay />

      {/* Floating orbs — deeper, more cinematic */}
      <Orb color="rgba(56, 139, 253, 0.06)" size={600} top="-15%" left="-10%" anim={1} />
      <Orb color="rgba(30, 100, 200, 0.05)" size={500} top="55%" left="65%" anim={2} />
      <Orb color="rgba(6, 182, 212, 0.03)" size={450} top="20%" left="40%" anim={3} />
      <Orb color="rgba(14, 165, 233, 0.025)" size={350} top="70%" left="15%" anim={1} />

      <GlassCard shaking={shaking}>
        {/* Logo */}
        <Box sx={{ textAlign: "center", mb: 3 }}>
          <Box
            component="img"
            src="/admin/assets/images/restai-logo.png"
            alt={appName}
            sx={{
              width: 180,
              height: 180,
              mb: 0.5,
              animation: `${logoPulse} 4s ease-in-out infinite`,
            }}
          />
          <Typography
            sx={{
              fontSize: "1.8rem",
              fontWeight: 800,
              letterSpacing: "-0.03em",
              background: `linear-gradient(90deg, #e2e8f0 0%, #58a6ff 40%, #79c0ff 60%, #e2e8f0 100%)`,
              backgroundSize: "200% auto",
              animation: `${shimmer} 4s linear infinite`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
            }}
          >
            {appName}
          </Typography>
        </Box>

        {/* Error */}
        <Collapse in={!!error}>
          <Alert
            severity="error"
            onClose={() => setError("")}
            sx={{
              mb: 2.5,
              borderRadius: 3,
              backgroundColor: "rgba(239, 68, 68, 0.08)",
              border: "1px solid rgba(239, 68, 68, 0.15)",
              color: "#fca5a5",
              backdropFilter: "blur(8px)",
              "& .MuiAlert-icon": { color: "#f87171" },
              "& .MuiAlert-action .MuiIconButton-root": { color: "#fca5a5" },
            }}
          >
            {error}
          </Alert>
        </Collapse>

        {/* TOTP */}
        {type === "totp" ? (
          <form onSubmit={handleTotpSubmit}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
              <LockIcon sx={{ color: "#79c0ff", fontSize: 20 }} />
              <Typography sx={{ fontWeight: 600, fontSize: "1rem" }}>Two-Factor Authentication</Typography>
            </Box>
            <Typography sx={{ fontSize: "0.85rem", color: "rgba(255,255,255,0.4)", mb: 2.5 }}>
              {useRecovery ? "Enter one of your recovery codes." : "Enter the 6-digit code from your authenticator app."}
            </Typography>
            <StyledInput
              fullWidth autoFocus
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
              sx={{ mb: 2, textTransform: "none", color: "#79c0ff", fontSize: "0.8rem", "&:hover": { backgroundColor: "rgba(99,102,241,0.06)" } }}
            >
              {useRecovery ? "Use authenticator code" : "Use a recovery code"}
            </Button>
            <PrimaryButton type="submit" loading={loading} variant="contained" fullWidth>Verify</PrimaryButton>
            <Button
              fullWidth size="small"
              onClick={() => { setType(null); setTotpToken(null); setTotpCode(""); setLoading(false); setError(""); }}
              sx={{ mt: 1.5, textTransform: "none", color: "rgba(255,255,255,0.3)", fontSize: "0.8rem", "&:hover": { color: "rgba(255,255,255,0.6)" } }}
            >
              Back to login
            </Button>
          </form>
        ) : (
          <>
            {/* Local Login */}
            {!authDisableLocal && (
              <form onSubmit={handleSubmit}>
                <StyledInput fullWidth autoFocus name="email" label="Username or Email" onChange={handleChange} sx={{ mb: 2 }} />
                <Collapse in={type === "password"}>
                  <StyledInput fullWidth name="password" type="password" label="Password" onChange={handleChange} sx={{ mb: 2 }} />
                </Collapse>
                <Box sx={{ display: "flex", alignItems: "center", mb: 2.5 }}>
                  <FormControlLabel
                    control={
                      <Checkbox size="small" name="remember" onChange={handleChange} checked={state.remember || false}
                        sx={{ color: "rgba(255,255,255,0.15)", "&.Mui-checked": { color: "#79c0ff" } }}
                      />
                    }
                    label={<Typography sx={{ fontSize: "0.82rem", color: "rgba(255,255,255,0.35)" }}>Remember me</Typography>}
                  />
                </Box>
                <PrimaryButton type="submit" loading={loading} variant="contained" fullWidth>
                  {type === null ? "Continue" : "Sign In"}
                </PrimaryButton>
              </form>
            )}

            {/* SSO */}
            {ssoProviders.length > 0 && (
              <>
                {!authDisableLocal && (
                  <OrDivider>
                    <Typography sx={{ fontSize: "0.7rem", color: "rgba(255,255,255,0.2)", letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 500 }}>
                      or
                    </Typography>
                  </OrDivider>
                )}
                <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                  {ssoProviders.map((provider) => (
                    <SSOButton
                      key={provider} variant="outlined" fullWidth
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
