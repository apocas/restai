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
            <DetailItem label="Knowledge Graph">
              <Chip
                label={project.options?.enable_knowledge_graph ? "Enabled" : "Disabled"}
                size="small"
                color={project.options?.enable_knowledge_graph ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            <DetailItem label="Logging">
              <Chip
                label={project.options?.logging !== false ? "Enabled" : "Disabled"}
                size="small"
                color={project.options?.logging !== false ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            {project.options?.rate_limit && (
              <DetailItem label="Rate Limit">
                <Typography variant="body2">{project.options.rate_limit} req/min</Typography>
              </DetailItem>
            )}
            {project.options?.fallback_llm && (
              <DetailItem label="Fallback LLM">
                <Typography variant="body2" fontFamily="monospace">{project.options.fallback_llm}</Typography>
              </DetailItem>
            )}
            {project.guard && (
              <DetailItem label="Input Guard">
                <Chip label={project.guard} size="small" color="warning" variant="outlined" />
              </DetailItem>
            )}
            {project.options?.guard_output && (
              <DetailItem label="Output Guard">
                <Chip label={project.options.guard_output} size="small" color="warning" variant="outlined" />
              </DetailItem>
            )}
            {(project.guard || project.options?.guard_output) && (
              <DetailItem label="Guard Mode">
                <Chip
                  label={project.options?.guard_mode === "warn" ? "Warn" : "Block"}
                  size="small"
                  color={project.options?.guard_mode === "warn" ? "info" : "error"}
                  variant="outlined"
                />
              </DetailItem>
            )}
            {project.censorship && (
              <DetailItem label="Censorship Message">
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
                  {project.censorship.length > 80 ? project.censorship.slice(0, 80) + "…" : project.censorship}
                </Typography>
              </DetailItem>
            )}
            <DetailItem label="Auto-Sync">
              {project.options?.sync_enabled && project.options?.sync_sources?.length > 0 ? (
                <Chip
                  label={`Active (${project.options.sync_sources.length} source${project.options.sync_sources.length > 1 ? "s" : ""})`}
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
