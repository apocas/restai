import { Article } from "@mui/icons-material";
import { Card, Chip, Grid, Typography, styled, Box } from "@mui/material";

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
  <Grid item xs={6} sm={6} md={4}>
    <Typography variant="caption" color="text.secondary" display="block">{label}</Typography>
    {children}
  </Grid>
);

export default function ProjectRAG({ project }) {
  return (
    <Card elevation={1} sx={{ p: 2.5 }}>
      <SectionTitle><Article fontSize="small" /> RAG</SectionTitle>
      <Grid container spacing={2}>
        <DetailItem label="Documents">
          <Typography variant="body2" fontWeight="bold">{project.chunks}</Typography>
        </DetailItem>
        <DetailItem label="Vectorstore">
          <Chip label={project.vectorstore} size="small" variant="outlined" />
        </DetailItem>
        <DetailItem label="Embeddings">
          <Typography variant="body2" fontFamily="monospace" sx={{ wordBreak: "break-word" }}>{project.embeddings}</Typography>
        </DetailItem>
        <DetailItem label="K">
          <Typography variant="body2">{project.options?.k}</Typography>
        </DetailItem>
        <DetailItem label="Cutoff">
          <Typography variant="body2">{project.options?.score}</Typography>
        </DetailItem>
        <DetailItem label="ColBERT Rerank">
          <Chip label={project.options?.colbert_rerank ? "Enabled" : "Disabled"} size="small"
            color={project.options?.colbert_rerank ? "success" : "default"} variant="outlined" />
        </DetailItem>
        <DetailItem label="LLM Rerank">
          <Chip label={project.options?.llm_rerank ? "Enabled" : "Disabled"} size="small"
            color={project.options?.llm_rerank ? "success" : "default"} variant="outlined" />
        </DetailItem>
        <DetailItem label="Cache">
          <Chip label={project.options?.cache ? "Enabled" : "Disabled"} size="small"
            color={project.options?.cache ? "success" : "default"} variant="outlined" />
        </DetailItem>
        {project.options?.cache && (
          <DetailItem label="Cache Threshold">
            <Typography variant="body2">{project.options?.cache_threshold ?? 0.85}</Typography>
          </DetailItem>
        )}
      </Grid>
    </Card>
  );
}
