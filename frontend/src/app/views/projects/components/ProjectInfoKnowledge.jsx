import { Card, Chip, Grid, Typography, styled } from "@mui/material";
import { Storage } from "@mui/icons-material";
import RAGUpload from "./RAGUpload";
import RAGBrowser from "./RAGBrowser";
import RAGRetrieval from "./RAGRetrieval";

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

export default function ProjectInfoKnowledge({ project }) {
  return (
    <Grid container spacing={3}>
      {/* RAG Settings */}
      <Grid item xs={12}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <SectionTitle><Storage fontSize="small" /> RAG Settings</SectionTitle>
          <Grid container spacing={2}>
            <DetailItem label="Documents">
              <Typography variant="body2" fontWeight="bold">
                {project.chunks ?? 0}
              </Typography>
            </DetailItem>
            {project.embeddings && (
              <DetailItem label="Embeddings">
                <Typography variant="body2" fontFamily="monospace">
                  {project.embeddings}
                </Typography>
              </DetailItem>
            )}
            {project.vectorstore && (
              <DetailItem label="Vector Store">
                <Chip label={project.vectorstore} size="small" variant="outlined" />
              </DetailItem>
            )}
            <DetailItem label="Top-K Documents">
              <Typography variant="body2">{project.options?.k ?? 4}</Typography>
            </DetailItem>
            <DetailItem label="Score Cutoff">
              <Typography variant="body2">{project.options?.score ?? 0.0}</Typography>
            </DetailItem>
            <DetailItem label="ColBERT Rerank">
              <Chip
                label={project.options?.colbert_rerank ? "Enabled" : "Disabled"}
                size="small"
                color={project.options?.colbert_rerank ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            <DetailItem label="LLM Rerank">
              <Chip
                label={project.options?.llm_rerank ? "Enabled" : "Disabled"}
                size="small"
                color={project.options?.llm_rerank ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            <DetailItem label="Cache">
              <Chip
                label={project.options?.cache ? "Enabled" : "Disabled"}
                size="small"
                color={project.options?.cache ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            {project.options?.cache && (
              <DetailItem label="Cache Threshold">
                <Typography variant="body2">
                  {project.options.cache_threshold ?? 0.85}
                </Typography>
              </DetailItem>
            )}
            {project.options?.connection && (
              <DetailItem label="SQL Connection">
                <Chip label="Configured" size="small" color="info" variant="outlined" />
              </DetailItem>
            )}
            {project.options?.tables && (
              <DetailItem label="SQL Tables">
                <Typography variant="body2" fontFamily="monospace">
                  {project.options.tables}
                </Typography>
              </DetailItem>
            )}
            <DetailItem label="Auto-Sync">
              {project.options?.sync_enabled && project.options?.sync_sources?.length > 0 ? (
                <Chip
                  label={`Active (${project.options.sync_sources.length} source${
                    project.options.sync_sources.length > 1 ? "s" : ""
                  }, every ${
                    project.options.sync_interval >= 1440
                      ? `${Math.round(project.options.sync_interval / 1440)}d`
                      : project.options.sync_interval >= 60
                      ? `${Math.round(project.options.sync_interval / 60)}h`
                      : `${project.options.sync_interval}m`
                  })`}
                  size="small"
                  color="success"
                  variant="outlined"
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Disabled
                </Typography>
              )}
            </DetailItem>
            {project.options?.last_sync && (
              <DetailItem label="Last Sync">
                <Typography variant="body2">
                  {new Date(project.options.last_sync).toLocaleString()}
                </Typography>
              </DetailItem>
            )}
          </Grid>
        </Card>
      </Grid>

      {/* RAG Upload */}
      <Grid item lg={4} md={6} xs={12}>
        <RAGUpload project={project} />
      </Grid>

      {/* RAG Browser */}
      {project.chunks < 30000 && (
        <Grid item xs={12}>
          <RAGBrowser project={project} />
        </Grid>
      )}

      {/* RAG Retrieval */}
      <Grid item xs={12}>
        <RAGRetrieval project={project} />
      </Grid>
    </Grid>
  );
}
