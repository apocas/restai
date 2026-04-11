import { useState, useEffect } from "react";
import {
  Box, Button, Card, Chip, FormControlLabel, Grid, IconButton, InputAdornment,
  Switch, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import {
  ArrowBack, CheckCircle, Visibility, VisibilityOff, PersonAdd,
  AdminPanelSettings, Lock, Shield, Check, Close,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

const Hero = styled(Box)(() => ({
  padding: "32px 0 24px",
  textAlign: "center",
}));

const HeroTitle = styled(Typography)(() => ({
  fontWeight: 700,
  letterSpacing: "-0.3px",
}));

const FormCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(4),
  borderRadius: 16,
  border: "1px solid",
  borderColor: theme.palette.divider,
  background: theme.palette.mode === "dark" ? "#1a1a24" : "#ffffff",
}));

const SectionLabel = styled(Typography)(({ theme }) => ({
  fontSize: "0.72rem",
  fontWeight: 700,
  textTransform: "uppercase",
  letterSpacing: "0.8px",
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1.5),
  display: "flex",
  alignItems: "center",
  gap: 6,
}));

const Dot = styled("span", {
  shouldForwardProp: (prop) => prop !== "color",
})(({ theme, color }) => ({
  width: 8,
  height: 8,
  borderRadius: "50%",
  background: color || theme.palette.primary.main,
  display: "inline-block",
}));

const PermissionRow = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "flex-start",
  gap: theme.spacing(2),
  padding: theme.spacing(2),
  borderRadius: 12,
  border: "1px solid",
  borderColor: theme.palette.divider,
  transition: "all 0.2s ease",
  "&:hover": {
    borderColor: theme.palette.primary.main,
    backgroundColor: theme.palette.action.hover,
  },
}));

const IconWrap = styled(Box, {
  shouldForwardProp: (prop) => prop !== "color",
})(({ color }) => ({
  width: 40,
  height: 40,
  borderRadius: 10,
  flexShrink: 0,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  background: `${color}14`,
  border: `1px solid ${color}33`,
}));

const RequirementRow = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "4px 0",
  fontSize: "0.85rem",
}));

export default function UserNewView() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [state, setState] = useState({
    username: "",
    password: "",
    confirmPassword: "",
    is_admin: false,
    is_private: false,
    is_restricted: false,
  });
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - New User";
  }, []);

  const pwd = state.password;
  const requirements = [
    { ok: pwd.length >= 8, label: "At least 8 characters" },
    { ok: /[a-z]/.test(pwd), label: "One lowercase letter" },
    { ok: /[A-Z]/.test(pwd), label: "One uppercase letter" },
    { ok: /[0-9\W_]/.test(pwd), label: "One number or symbol" },
  ];
  const pwdStrength = requirements.filter((r) => r.ok).length;
  const strengthLabel = ["Too weak", "Weak", "Fair", "Good", "Strong"][pwdStrength];
  const strengthColor = ["#ef4444", "#f59e0b", "#f59e0b", "#10b981", "#10b981"][pwdStrength];

  const passwordsMatch = state.confirmPassword === "" || state.password === state.confirmPassword;

  const handleChange = (e) => {
    const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setState({ ...state, [e.target.name]: value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!state.username.trim()) return toast.error("Username is required");
    if (!state.password) return toast.error("Password is required");
    if (state.password !== state.confirmPassword) return toast.error("Passwords do not match");
    if (state.password.length < 8) return toast.error("Password must be at least 8 characters");

    setLoading(true);
    try {
      const response = await api.post("/users", {
        username: state.username,
        password: state.password,
        is_admin: state.is_admin,
        is_private: state.is_private,
        is_restricted: state.is_restricted,
      }, auth.user.token);
      navigate("/user/" + response.username);
    } catch {
      // toasted
    } finally {
      setLoading(false);
    }
  };

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Users", path: "/users" }, { name: "New User" }]} />
      </Box>

      <Hero>
        <Box sx={{ position: "relative", zIndex: 1 }}>
          <HeroTitle variant="h4" color="primary" sx={{ mb: 1 }}>
            Create a new user
          </HeroTitle>
          <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 520, mx: "auto" }}>
            Add a user to the platform. Set their credentials and permission level.
          </Typography>
        </Box>
      </Hero>

      <Box sx={{ maxWidth: 960, mx: "auto" }}>
        <form onSubmit={handleSubmit}>
          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#6366f1" />
              Account
            </SectionLabel>
            <Grid container spacing={2.5}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  required
                  autoFocus
                  size="small"
                  name="username"
                  label="Username"
                  value={state.username}
                  onChange={handleChange}
                  placeholder="e.g. alice"
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  size="small"
                  type={showPassword ? "text" : "password"}
                  name="password"
                  label="Password"
                  value={state.password}
                  onChange={handleChange}
                  InputProps={{
                    endAdornment: (
                      <InputAdornment position="end">
                        <IconButton size="small" onClick={() => setShowPassword(!showPassword)}>
                          {showPassword ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                        </IconButton>
                      </InputAdornment>
                    ),
                  }}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  size="small"
                  type={showPassword ? "text" : "password"}
                  name="confirmPassword"
                  label="Confirm Password"
                  value={state.confirmPassword}
                  onChange={handleChange}
                  error={!passwordsMatch}
                  helperText={!passwordsMatch ? "Passwords do not match" : ""}
                />
              </Grid>

              {/* Strength meter */}
              {pwd && (
                <Grid item xs={12}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 1.5 }}>
                    <Box sx={{ flex: 1, display: "flex", gap: 0.5 }}>
                      {[0, 1, 2, 3].map((i) => (
                        <Box
                          key={i}
                          sx={{
                            flex: 1,
                            height: 4,
                            borderRadius: 2,
                            background: i < pwdStrength ? strengthColor : "rgba(0,0,0,0.08)",
                            transition: "background 0.2s",
                          }}
                        />
                      ))}
                    </Box>
                    <Typography variant="caption" sx={{ color: strengthColor, fontWeight: 600, minWidth: 60 }}>
                      {strengthLabel}
                    </Typography>
                  </Box>
                  <Grid container spacing={0.5}>
                    {requirements.map((r) => (
                      <Grid item xs={12} sm={6} key={r.label}>
                        <RequirementRow>
                          {r.ok ? (
                            <Check sx={{ fontSize: 16, color: "#10b981" }} />
                          ) : (
                            <Close sx={{ fontSize: 16, color: "text.disabled" }} />
                          )}
                          <Typography
                            variant="caption"
                            sx={{ color: r.ok ? "text.primary" : "text.disabled" }}
                          >
                            {r.label}
                          </Typography>
                        </RequirementRow>
                      </Grid>
                    ))}
                  </Grid>
                </Grid>
              )}
            </Grid>
          </FormCard>

          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#10b981" />
              Permissions
            </SectionLabel>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              <PermissionRow>
                <IconWrap color="#ef4444">
                  <AdminPanelSettings sx={{ fontSize: 22, color: "#ef4444" }} />
                </IconWrap>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    Administrator
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Full access to all projects, users, teams, and platform settings.
                  </Typography>
                </Box>
                <Switch
                  checked={state.is_admin}
                  name="is_admin"
                  onChange={handleChange}
                />
              </PermissionRow>

              <PermissionRow>
                <IconWrap color="#f59e0b">
                  <Shield sx={{ fontSize: 22, color: "#f59e0b" }} />
                </IconWrap>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    Read-only access
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    User can only chat with existing projects. No creating, editing, ingesting, or direct access.
                  </Typography>
                </Box>
                <Switch
                  checked={state.is_restricted}
                  name="is_restricted"
                  onChange={handleChange}
                />
              </PermissionRow>

              <PermissionRow>
                <IconWrap color="#6366f1">
                  <Lock sx={{ fontSize: 22, color: "#6366f1" }} />
                </IconWrap>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    Local AI only
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Restrict this user to on-premise LLMs and embeddings — no external provider calls.
                  </Typography>
                </Box>
                <Switch
                  checked={state.is_private}
                  name="is_private"
                  onChange={handleChange}
                />
              </PermissionRow>
            </Box>
          </FormCard>

          <Box sx={{ display: "flex", justifyContent: "flex-end", gap: 1.5 }}>
            <Button variant="outlined" onClick={() => navigate("/users")}>
              Cancel
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={loading}
              startIcon={<PersonAdd />}
            >
              {loading ? "Creating..." : "Create User"}
            </Button>
          </Box>
        </form>
      </Box>
    </Container>
  );
}
