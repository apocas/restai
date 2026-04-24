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
import { useTranslation } from "react-i18next";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import api from "app/utils/api";
import { colors } from "app/utils/themeColors";

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
  const { t } = useTranslation();
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
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("users.newPage.browserTitle");
  }, [t]);

  const pwd = state.password;
  const requirements = [
    { ok: pwd.length >= 8, label: t("users.pwReq.chars") },
    { ok: /[a-z]/.test(pwd), label: t("users.pwReq.lower") },
    { ok: /[A-Z]/.test(pwd), label: t("users.pwReq.upper") },
    { ok: /[0-9\W_]/.test(pwd), label: t("users.pwReq.digit") },
  ];
  const pwdStrength = requirements.filter((r) => r.ok).length;
  const strengthLabel = [t("users.pwReq.tooWeak"), t("users.pwReq.weak"), t("users.pwReq.fair"), t("users.pwReq.good"), t("users.pwReq.strong")][pwdStrength];
  const strengthColor = [
    colors.status.error, colors.status.warning, colors.status.warning,
    colors.status.success, colors.status.success,
  ][pwdStrength];

  const passwordsMatch = state.confirmPassword === "" || state.password === state.confirmPassword;

  const handleChange = (e) => {
    const value = e.target.type === "checkbox" ? e.target.checked : e.target.value;
    setState({ ...state, [e.target.name]: value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!state.username.trim()) return toast.error(t("users.newPage.usernameRequired"));
    if (!state.password) return toast.error(t("users.newPage.passwordRequired"));
    if (state.password !== state.confirmPassword) return toast.error(t("users.newPage.passwordsMismatch"));
    if (state.password.length < 8) return toast.error(t("users.newPage.passwordMin"));

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
        <Breadcrumb routeSegments={[{ name: t("nav.users"), path: "/users" }, { name: t("users.new") }]} />
      </Box>

      <Hero>
        <Box sx={{ position: "relative", zIndex: 1 }}>
          <HeroTitle variant="h4" color="primary" sx={{ mb: 1 }}>
            {t("users.newPage.title")}
          </HeroTitle>
          <Typography variant="body1" color="text.secondary" sx={{ maxWidth: 520, mx: "auto" }}>
            {t("users.newPage.subtitle")}
          </Typography>
        </Box>
      </Hero>

      <Box sx={{ maxWidth: 960, mx: "auto" }}>
        <form onSubmit={handleSubmit}>
          <FormCard sx={{ mb: 3 }}>
            <SectionLabel>
              <Dot color="#6366f1" />
              {t("users.newPage.account")}
            </SectionLabel>
            <Grid container spacing={2.5}>
              <Grid item xs={12}>
                <TextField
                  fullWidth
                  required
                  autoFocus
                  size="small"
                  name="username"
                  label={t("users.fields.username")}
                  value={state.username}
                  onChange={handleChange}
                  placeholder={t("users.newPage.usernamePlaceholder")}
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  size="small"
                  type={showPassword ? "text" : "password"}
                  name="password"
                  label={t("users.fields.password")}
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
                  label={t("users.fields.confirmPassword")}
                  value={state.confirmPassword}
                  onChange={handleChange}
                  error={!passwordsMatch}
                  helperText={!passwordsMatch ? t("users.newPage.passwordsMismatch") : ""}
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
                            <Check sx={{ fontSize: 16, color: colors.status.success }} />
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
              <Dot color={colors.status.success} />
              {t("users.newPage.permissions")}
            </SectionLabel>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1.5 }}>
              <PermissionRow>
                <IconWrap color={colors.status.error}>
                  <AdminPanelSettings sx={{ fontSize: 22, color: colors.status.error }} />
                </IconWrap>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    {t("users.fields.isAdmin")}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t("users.newPage.adminHelp")}
                  </Typography>
                </Box>
                <Switch
                  checked={state.is_admin}
                  name="is_admin"
                  onChange={handleChange}
                />
              </PermissionRow>

              <PermissionRow>
                <IconWrap color={colors.status.warning}>
                  <Shield sx={{ fontSize: 22, color: colors.status.warning }} />
                </IconWrap>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    {t("users.fields.isRestricted")}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t("users.newPage.restrictedHelp")}
                  </Typography>
                </Box>
                <Switch
                  checked={state.is_restricted}
                  name="is_restricted"
                  onChange={handleChange}
                />
              </PermissionRow>

              <PermissionRow>
                <IconWrap color={colors.status.info}>
                  <Lock sx={{ fontSize: 22, color: colors.status.info }} />
                </IconWrap>
                <Box sx={{ flex: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600}>
                    {t("users.fields.isPrivate")}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t("users.newPage.privateHelp")}
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
              {t("common.cancel")}
            </Button>
            <Button
              type="submit"
              variant="contained"
              disabled={loading}
              startIcon={<PersonAdd />}
            >
              {loading ? t("users.newPage.creating") : t("users.newPage.create")}
            </Button>
          </Box>
        </form>
      </Box>
    </Container>
  );
}
