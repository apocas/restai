import { Box, Typography, styled } from "@mui/material";
import {
  CloudDownload, Tune, ArrowForward, Bolt, CheckCircle,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Breadcrumb from "app/components/Breadcrumb";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

const Hero = styled(Box)(() => ({
  padding: "48px 0 40px",
  textAlign: "center",
}));

const OptionCard = styled(Box, {
  shouldForwardProp: (prop) => prop !== "accent",
})(({ theme, accent }) => ({
  position: "relative",
  cursor: "pointer",
  transition: "all 0.25s ease",
  borderRadius: 16,
  padding: 32,
  background: theme.palette.mode === "dark" ? "#1a1a24" : "#ffffff",
  border: "1px solid",
  borderColor: theme.palette.divider,
  overflow: "hidden",
  display: "flex",
  flexDirection: "column",
  minHeight: 340,
  "&::before": {
    content: '""',
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: 3,
    background: `linear-gradient(90deg, ${accent}, ${accent}00)`,
    opacity: 0,
    transition: "opacity 0.25s",
  },
  "&:hover": {
    borderColor: accent,
    transform: "translateY(-4px)",
    boxShadow: `0 20px 40px -12px ${accent}33`,
    "&::before": { opacity: 1 },
    "& .arrow-btn": {
      backgroundColor: accent,
      color: "#fff",
      transform: "translateX(4px)",
    },
    "& .icon-box": {
      transform: "scale(1.05) rotate(-3deg)",
    },
  },
}));

const IconBox = styled(Box, {
  shouldForwardProp: (prop) => prop !== "accent",
})(({ accent }) => ({
  width: 64,
  height: 64,
  borderRadius: 16,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  marginBottom: 20,
  background: `linear-gradient(135deg, ${accent}22, ${accent}0a)`,
  border: `1px solid ${accent}33`,
  transition: "transform 0.3s ease",
}));

const ArrowButton = styled(Box)(({ theme }) => ({
  width: 40,
  height: 40,
  borderRadius: 10,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  backgroundColor: theme.palette.action.hover,
  color: theme.palette.text.secondary,
  transition: "all 0.25s ease",
  marginTop: "auto",
  alignSelf: "flex-end",
}));

const FeatureRow = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: 8,
  padding: "4px 0",
  fontSize: "0.85rem",
  color: theme.palette.text.secondary,
}));

const BadgeChip = styled(Box, {
  shouldForwardProp: (prop) => prop !== "color",
})(({ color }) => ({
  display: "inline-flex",
  alignItems: "center",
  gap: 4,
  padding: "3px 10px",
  borderRadius: 20,
  fontSize: "0.7rem",
  fontWeight: 700,
  letterSpacing: "0.3px",
  textTransform: "uppercase",
  background: `${color}1a`,
  color: color,
  border: `1px solid ${color}33`,
  marginBottom: 12,
  width: "fit-content",
}));

function Option({ accent, badge, badgeIcon, icon: Icon, title, description, features, onClick }) {
  return (
    <OptionCard accent={accent} onClick={onClick}>
      <IconBox className="icon-box" accent={accent}>
        <Icon sx={{ fontSize: 30, color: accent }} />
      </IconBox>

      {badge && (
        <BadgeChip color={accent}>
          {badgeIcon}
          {badge}
        </BadgeChip>
      )}

      <Typography variant="h5" fontWeight={700} sx={{ mb: 1 }}>
        {title}
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5, lineHeight: 1.6 }}>
        {description}
      </Typography>

      <Box sx={{ mb: 2 }}>
        {features.map((f) => (
          <FeatureRow key={f}>
            <CheckCircle sx={{ fontSize: 16, color: accent }} />
            {f}
          </FeatureRow>
        ))}
      </Box>

      <ArrowButton className="arrow-btn">
        <ArrowForward sx={{ fontSize: 20 }} />
      </ArrowButton>
    </OptionCard>
  );
}

export default function NewChooser() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: t("nav.embeddings"), path: "/embeddings" },
            { name: t("embeddings.newBreadcrumb") },
          ]}
        />
      </Box>

      <Hero>
        <Box sx={{ position: "relative", zIndex: 1 }}>
          <Typography
            variant="h4"
            fontWeight={700}
            color="primary"
            sx={{ mb: 1, letterSpacing: "-0.3px" }}
          >
            {t("embeddings.chooser.title")}
          </Typography>
          <Typography
            variant="body1"
            color="text.secondary"
            sx={{ maxWidth: 560, mx: "auto" }}
          >
            {t("embeddings.chooser.subtitle")}
          </Typography>
        </Box>
      </Hero>

      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
          gap: 3,
          maxWidth: 960,
          mx: "auto",
          pb: 6,
          position: "relative",
          zIndex: 1,
        }}
      >
        <Option
          accent="#10b981"
          badge={t("embeddings.chooser.fastest")}
          badgeIcon={<Bolt sx={{ fontSize: 12 }} />}
          icon={CloudDownload}
          title={t("embeddings.chooser.ollama")}
          description={t("embeddings.chooser.ollamaDesc")}
          features={[
            t("embeddings.chooser.featAutoDim"),
            t("embeddings.chooser.featCapability"),
            t("embeddings.chooser.featZeroConfig"),
            t("embeddings.chooser.featBulk"),
          ]}
          onClick={() => navigate("/llms/ollama")}
        />

        <Option
          accent="#6366f1"
          icon={Tune}
          title={t("embeddings.chooser.manual")}
          description={t("embeddings.chooser.manualDesc")}
          features={[
            t("embeddings.chooser.featMulti"),
            t("embeddings.chooser.featHf"),
            t("embeddings.chooser.featFineGrain"),
            t("embeddings.chooser.featCredentials"),
          ]}
          onClick={() => navigate("/embeddings/new/manual")}
        />
      </Box>
    </Container>
  );
}
