import { Card, Chip, Grid, Typography, styled } from "@mui/material";
import { Shield } from "@mui/icons-material";

const SectionTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  fontSize: "0.9rem",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.5),
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1),
}));

const DetailItem = ({ label, children }) => (
  <Grid item xs={12} sm={6} md={4}>
    <Typography variant="caption" color="text.secondary" display="block">
      {label}
    </Typography>
    {children}
  </Grid>
);

export default function ProjectInfoSecurity({ project }) {
  return (
    <Grid container spacing={3}>
      <Grid item xs={12}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <SectionTitle><Shield fontSize="small" /> Security</SectionTitle>
          <Grid container spacing={2}>
            <DetailItem label="Input Guard">
              {project.guard ? (
                <Chip label={project.guard} size="small" color="warning" variant="outlined" />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Disabled
                </Typography>
              )}
            </DetailItem>
            <DetailItem label="Output Guard">
              {project.options?.guard_output ? (
                <Chip
                  label={project.options.guard_output}
                  size="small"
                  color="warning"
                  variant="outlined"
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Disabled
                </Typography>
              )}
            </DetailItem>
            {project.options?.guard_mode && (project.guard || project.options?.guard_output) && (
              <DetailItem label="Guard Mode">
                <Chip
                  label={project.options.guard_mode === "warn" ? "Warn" : "Block"}
                  size="small"
                  color={project.options.guard_mode === "warn" ? "warning" : "error"}
                  variant="outlined"
                />
              </DetailItem>
            )}
            {project.censorship && (
              <Grid item xs={12} sm={8}>
                <Typography variant="caption" color="text.secondary" display="block">
                  Censorship Message
                </Typography>
                <Typography
                  variant="body2"
                  sx={{
                    display: "-webkit-box",
                    WebkitLineClamp: 3,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                    fontStyle: "italic",
                    bgcolor: "action.hover",
                    p: 1,
                    borderRadius: 1,
                    mt: 0.5,
                  }}
                >
                  {project.censorship}
                </Typography>
              </Grid>
            )}
          </Grid>
        </Card>
      </Grid>
    </Grid>
  );
}
