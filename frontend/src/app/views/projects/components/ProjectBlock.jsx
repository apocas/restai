import { Card, Chip, Grid, Typography, styled } from "@mui/material";
import ViewInArIcon from "@mui/icons-material/ViewInAr";

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
  <Grid item xs={6} sm={4}>
    <Typography variant="caption" color="text.secondary" display="block">{label}</Typography>
    {children}
  </Grid>
);

export default function ProjectBlock({ project }) {
  const workspace = project.options?.blockly_workspace;
  const blockCount = workspace?.blocks?.blocks?.length ?? 0;
  const variableCount = workspace?.variables?.length ?? 0;
  const hasWorkspace = !!workspace;

  return (
    <Card elevation={1} sx={{ p: 2.5 }}>
      <SectionTitle><ViewInArIcon fontSize="small" /> Block Configuration</SectionTitle>
      <Grid container spacing={2}>
        <DetailItem label="Status">
          <Chip label={hasWorkspace ? "Configured" : "Not configured"} size="small"
            color={hasWorkspace ? "success" : "default"} variant="outlined" />
        </DetailItem>
        <DetailItem label="Top-level Blocks">
          <Typography variant="body2">{blockCount}</Typography>
        </DetailItem>
        <DetailItem label="Variables">
          <Typography variant="body2">{variableCount}</Typography>
        </DetailItem>
      </Grid>
    </Card>
  );
}
