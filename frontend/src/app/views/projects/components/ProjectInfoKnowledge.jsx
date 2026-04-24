import { Card, Chip, Grid, Typography, styled } from "@mui/material";
import { Storage } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
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
  const { t } = useTranslation();
  return (
    <Grid container spacing={3}>
      {/* RAG Settings */}
      <Grid item xs={12}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <SectionTitle><Storage fontSize="small" /> {t("projects.knowledge.infoKnowledge.title")}</SectionTitle>
          <Grid container spacing={2}>
            <DetailItem label={t("projects.knowledge.infoKnowledge.documents")}>
              <Typography variant="body2" fontWeight="bold">
                {project.chunks ?? 0}
              </Typography>
            </DetailItem>
            {project.embeddings && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.embeddings")}>
                <Typography variant="body2" fontFamily="monospace">
                  {project.embeddings}
                </Typography>
              </DetailItem>
            )}
            {project.vectorstore && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.vectorStore")}>
                <Chip label={project.vectorstore} size="small" variant="outlined" />
              </DetailItem>
            )}
            <DetailItem label={t("projects.knowledge.infoKnowledge.topK")}>
              <Typography variant="body2">{project.options?.k ?? 4}</Typography>
            </DetailItem>
            <DetailItem label={t("projects.knowledge.infoKnowledge.scoreCutoff")}>
              <Typography variant="body2">{project.options?.score ?? 0.0}</Typography>
            </DetailItem>
            <DetailItem label={t("projects.knowledge.infoKnowledge.colbertRerank")}>
              <Chip
                label={project.options?.colbert_rerank ? t("common.enabled") : t("common.disabled")}
                size="small"
                color={project.options?.colbert_rerank ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            <DetailItem label={t("projects.knowledge.infoKnowledge.llmRerank")}>
              <Chip
                label={project.options?.llm_rerank ? t("common.enabled") : t("common.disabled")}
                size="small"
                color={project.options?.llm_rerank ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            <DetailItem label={t("projects.knowledge.infoKnowledge.cache")}>
              <Chip
                label={project.options?.cache ? t("common.enabled") : t("common.disabled")}
                size="small"
                color={project.options?.cache ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            {project.options?.cache && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.cacheThreshold")}>
                <Typography variant="body2">
                  {project.options.cache_threshold ?? 0.85}
                </Typography>
              </DetailItem>
            )}
            {project.options?.connection && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.sqlConnection")}>
                <Chip label={t("projects.knowledge.infoKnowledge.configured")} size="small" color="info" variant="outlined" />
              </DetailItem>
            )}
            {project.options?.tables && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.sqlTables")}>
                <Typography variant="body2" fontFamily="monospace">
                  {project.options.tables}
                </Typography>
              </DetailItem>
            )}
            <DetailItem label={t("projects.knowledge.infoKnowledge.knowledgeGraph")}>
              <Chip
                label={project.options?.enable_knowledge_graph ? t("common.enabled") : t("common.disabled")}
                size="small"
                color={project.options?.enable_knowledge_graph ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            <DetailItem label={t("projects.knowledge.infoKnowledge.logging")}>
              <Chip
                label={project.options?.logging !== false ? t("common.enabled") : t("common.disabled")}
                size="small"
                color={project.options?.logging !== false ? "success" : "default"}
                variant="outlined"
              />
            </DetailItem>
            {project.options?.rate_limit && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.rateLimit")}>
                <Typography variant="body2">{t("projects.knowledge.infoKnowledge.rateLimitValue", { value: project.options.rate_limit })}</Typography>
              </DetailItem>
            )}
            {project.guard && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.inputGuard")}>
                <Chip label={project.guard} size="small" color="warning" variant="outlined" />
              </DetailItem>
            )}
            {project.options?.guard_output && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.outputGuard")}>
                <Chip label={project.options.guard_output} size="small" color="warning" variant="outlined" />
              </DetailItem>
            )}
            {(project.guard || project.options?.guard_output) && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.guardMode")}>
                <Chip
                  label={project.options?.guard_mode === "warn" ? t("projects.knowledge.infoKnowledge.guardWarn") : t("projects.knowledge.infoKnowledge.guardBlock")}
                  size="small"
                  color={project.options?.guard_mode === "warn" ? "info" : "error"}
                  variant="outlined"
                />
              </DetailItem>
            )}
            {project.censorship && (
              <DetailItem label={t("projects.knowledge.infoKnowledge.censorshipMessage")}>
                <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
                  {project.censorship.length > 80 ? project.censorship.slice(0, 80) + "…" : project.censorship}
                </Typography>
              </DetailItem>
            )}
            <DetailItem label={t("projects.knowledge.infoKnowledge.autoSync")}>
              {project.options?.sync_enabled && project.options?.sync_sources?.length > 0 ? (
                <Chip
                  label={t("projects.knowledge.infoKnowledge.autoSyncActive", { count: project.options.sync_sources.length })}
                  size="small"
                  color="success"
                  variant="outlined"
                />
              ) : (
                <Typography variant="body2" color="text.secondary">
                  {t("common.disabled")}
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
