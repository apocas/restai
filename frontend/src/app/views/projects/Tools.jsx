import { useState, useEffect } from "react";
import {
  Alert, Box, Card, Chip, Grid, InputAdornment, styled, TextField, Typography,
} from "@mui/material";
import { Search, Build, Block, Info } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function Tools() {
  const { t } = useTranslation();
  const [tools, setTools] = useState([]);
  const [search, setSearch] = useState("");
  const auth = useAuth();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - " + t("tools.breadcrumb");
    api.get("/tools/agent", auth.user.token)
      .then((d) => setTools(d || []))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t]);

  const filtered = tools.filter(
    (tl) =>
      tl.name.toLowerCase().includes(search.toLowerCase()) ||
      (tl.description || "").toLowerCase().includes(search.toLowerCase())
  );

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.projects"), path: "/projects" }, { name: t("tools.breadcrumb") }]} />
      </Box>

      <Box>
        <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between", mb: 2, flexWrap: "wrap", gap: 2 }}>
          <Box>
            <Typography variant="h5" fontWeight={700}>{t("tools.title")}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t("tools.subtitle")}
            </Typography>
          </Box>
          <Chip label={t("tools.toolCount", { count: tools.length })} variant="outlined" size="small" />
        </Box>

        <Alert severity="info" icon={<Info fontSize="small" />} sx={{ mb: 3 }}>
          {t("tools.info")}
        </Alert>

        <TextField
          fullWidth
          size="small"
          placeholder={t("tools.searchPlaceholder")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ mb: 3 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search fontSize="small" color="action" />
              </InputAdornment>
            ),
          }}
        />

        {filtered.length === 0 ? (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 4 }}>
            {search ? t("tools.noMatch") : t("tools.noTools")}
          </Typography>
        ) : (
          <Grid container spacing={2}>
            {filtered.map((tool) => (
              <Grid item xs={12} key={tool.name}>
                <Card
                  variant="outlined"
                  sx={{
                    p: 2.5,
                    borderRadius: "10px",
                    border: "1px solid",
                    borderColor: "divider",
                    opacity: tool.enabled === false ? 0.5 : 1,
                    "&:hover": tool.enabled !== false ? { borderColor: "primary.main", transition: "border-color 0.2s" } : {},
                  }}
                >
                  <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2 }}>
                    <Box
                      sx={{
                        width: 36, height: 36, borderRadius: "8px", flexShrink: 0,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        background: (theme) => tool.enabled === false
                          ? (theme.palette.mode === "dark" ? "rgba(150,150,150,0.15)" : "rgba(150,150,150,0.08)")
                          : (theme.palette.mode === "dark" ? "rgba(99,102,241,0.15)" : "rgba(99,102,241,0.08)"),
                      }}
                    >
                      {tool.enabled === false
                        ? <Block sx={{ fontSize: 18, color: "text.disabled" }} />
                        : <Build sx={{ fontSize: 18, color: "primary.main" }} />
                      }
                    </Box>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                        <Typography
                          variant="subtitle1"
                          fontWeight={600}
                          sx={{ fontFamily: "monospace", fontSize: "0.95rem" }}
                        >
                          {tool.name}
                        </Typography>
                        {tool.enabled === false && (
                          <Chip label={t("tools.requiresDocker")} size="small" color="warning" variant="outlined" sx={{ fontSize: "0.7rem", height: 22 }} />
                        )}
                      </Box>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mt: 0.5, whiteSpace: "pre-wrap", lineHeight: 1.6 }}
                      >
                        {tool.description}
                      </Typography>
                    </Box>
                  </Box>
                </Card>
              </Grid>
            ))}
          </Grid>
        )}
      </Box>
    </Container>
  );
}
