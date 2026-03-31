import { useState } from "react";
import {
  Box,
  Card,
  Chip,
  Grid,
  Typography,
  styled,
} from "@mui/material";
import {
  SmartToy, Description, ImageSearch, Summarize, Code,
  SupportAgent, DataObject, Translate, TravelExplore, AccountTree,
  Shield, AddCircleOutline,
} from "@mui/icons-material";
import { PROJECT_TEMPLATES, TEMPLATE_CATEGORIES } from "./projectTemplates";

const ICONS = {
  SmartToy, Description, ImageSearch, Summarize, Code,
  SupportAgent, DataObject, Translate, TravelExplore, AccountTree,
  Shield,
};

const TYPE_COLORS = {
  inference: "#1976d2",
  rag: "#2e7d32",
  agent: "#ed6c02",
  block: "#795548",
};

const TemplateCard = styled(Card)(({ theme }) => ({
  cursor: "pointer",
  padding: theme.spacing(3),
  height: "100%",
  display: "flex",
  flexDirection: "column",
  transition: "all 0.2s ease",
  "&:hover": {
    transform: "translateY(-4px)",
    boxShadow: theme.shadows[8],
  },
}));

const ScratchCard = styled(Card)(({ theme }) => ({
  cursor: "pointer",
  padding: theme.spacing(3),
  height: "100%",
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  justifyContent: "center",
  border: "2px dashed",
  borderColor: theme.palette.divider,
  backgroundColor: "transparent",
  transition: "all 0.2s ease",
  "&:hover": {
    transform: "translateY(-4px)",
    borderColor: theme.palette.primary.main,
    boxShadow: theme.shadows[4],
  },
}));

const IconCircle = styled(Box)({
  width: 48,
  height: 48,
  borderRadius: "50%",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  marginBottom: 12,
});

export default function TemplateGallery({ onSelect }) {
  const [category, setCategory] = useState("all");

  const filtered = category === "all"
    ? PROJECT_TEMPLATES
    : PROJECT_TEMPLATES.filter((t) => t.category === category);

  return (
    <Box>
      <Box sx={{ textAlign: "center", mb: 4 }}>
        <Typography variant="h4" fontWeight="bold" gutterBottom>
          Choose a Template
        </Typography>
        <Typography variant="body1" color="text.secondary">
          Start with a pre-configured project or build from scratch
        </Typography>
      </Box>

      <Box sx={{ display: "flex", justifyContent: "center", gap: 1, mb: 4, flexWrap: "wrap" }}>
        {TEMPLATE_CATEGORIES.map((cat) => (
          <Chip
            key={cat.id}
            label={cat.label}
            onClick={() => setCategory(cat.id)}
            color={category === cat.id ? "primary" : "default"}
            variant={category === cat.id ? "filled" : "outlined"}
          />
        ))}
      </Box>

      <Grid container spacing={3}>
        <Grid item xs={12} sm={6} md={4} lg={3}>
          <ScratchCard elevation={0} onClick={() => onSelect(null)}>
            <AddCircleOutline sx={{ fontSize: 48, color: "text.secondary", mb: 1 }} />
            <Typography variant="h6" color="text.secondary" gutterBottom>
              Start from Scratch
            </Typography>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              Create a blank project and configure everything manually
            </Typography>
          </ScratchCard>
        </Grid>

        {filtered.map((template) => {
          const IconComponent = ICONS[template.icon];
          return (
            <Grid item xs={12} sm={6} md={4} lg={3} key={template.id}>
              <TemplateCard elevation={2} onClick={() => onSelect(template)}>
                <IconCircle sx={{ backgroundColor: template.color }}>
                  {IconComponent && <IconComponent sx={{ color: "#fff", fontSize: 24 }} />}
                </IconCircle>
                <Typography variant="h6" gutterBottom>
                  {template.name}
                </Typography>
                <Chip
                  label={template.type}
                  size="small"
                  sx={{
                    mb: 1,
                    backgroundColor: TYPE_COLORS[template.type] || "#999",
                    color: "#fff",
                    alignSelf: "flex-start",
                  }}
                />
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{
                    flexGrow: 1,
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {template.description}
                </Typography>
              </TemplateCard>
            </Grid>
          );
        })}
      </Grid>
    </Box>
  );
}
