import { useState, useEffect } from "react";
import {
  Accordion, AccordionDetails, AccordionSummary, Avatar, Box, Button, Card, Chip,
  CircularProgress, Divider, Dialog, DialogTitle, DialogContent,
  DialogActions, Grid, IconButton, Stack, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import {
  Edit, Delete, Code, Article, SportsEsports, ViewInAr, Science, Security,
  ContentCopy, ClearAll, Speed, Shield, Cached, Groups, Psychology,
  Settings, Storage, Build, Chat, Notifications, ExpandMore,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import sha256 from "crypto-js/sha256";
import BAvatar from "boring-avatars";
import api from "app/utils/api";

const HeroCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(3),
  marginBottom: theme.spacing(2),
}));

const ActionBar = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(0.5),
  flexWrap: "wrap",
  marginTop: theme.spacing(2),
}));

const MetaItem = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: 4,
  color: theme.palette.text.secondary,
  fontSize: "0.85rem",
}));

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
    <Typography variant="caption" color="text.secondary" display="block">{label}</Typography>
    {children}
  </Grid>
);

const TYPE_COLORS = {
  inference: "primary",
  rag: "success",
  agent: "warning",
  block: "default",
};

export default function ProjectInfo({ project, projects, info }) {
  const navigate = useNavigate();
  const auth = useAuth();
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [health, setHealth] = useState(null);
  const [mcpTools, setMcpTools] = useState({});
  const [mcpLoading, setMcpLoading] = useState(false);

  useEffect(() => {
    if (project.id) {
      api.get("/projects/health", auth.user.token, { silent: true })
        .then((data) => {
          const h = (data || []).find((x) => x.project_id === project.id);
          if (h) setHealth(h);
        })
        .catch(() => {});

      if (project.type === "agent" && project.options?.mcp_servers?.length > 0) {
        setMcpLoading(true);
        api.get(`/projects/${project.id}/tools`, auth.user.token)
          .then((data) => setMcpTools(data.mcp_servers || {}))
          .catch(() => {})
          .finally(() => setMcpLoading(false));
      }
    }
  }, [project.id]);

  const handleClone = () => {
    if (!cloneName.trim()) return;
    api.post("/projects/" + project.id + "/clone", { name: cloneName.trim() }, auth.user.token)
      .then((response) => {
        setCloneOpen(false);
        setCloneName("");
        navigate("/project/" + response.project);
      })
      .catch(() => {});
  };

  const handleDelete = () => {
    if (window.confirm("Are you sure you want to delete " + project.name + "?")) {
      api.delete("/projects/" + project.id, auth.user.token)
        .then(() => navigate("/projects"))
        .catch(() => {});
    }
  };

  return (
    <>
      <HeroCard elevation={3}>
        {/* Header Row: Avatar + Name + Type + Health */}
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 2, flexWrap: "wrap" }}>
          <BAvatar name={project.name} size={64} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]} />

          <Box sx={{ flex: 1, minWidth: 200 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              <Typography variant="h5" fontWeight="bold">{project.human_name || project.name}</Typography>
              <Chip label={project.type} size="small" color={TYPE_COLORS[project.type] || "default"} />
              {health && (
                <Tooltip
                  title={
                    <Box>
                      <div><strong>Health: {health.health}/100</strong></div>
                      <div>Requests (7d): {health.requests_7d || 0}</div>
                      <div>Avg Latency: {health.avg_latency ? health.avg_latency + "ms" : "N/A"}</div>
                      <div>Guard Block Rate: {health.guard_block_rate !== null ? (health.guard_block_rate * 100).toFixed(1) + "%" : "N/A"}</div>
                      <div>Eval Score: {health.eval_score !== null ? (health.eval_score * 100).toFixed(0) + "%" : "N/A"}</div>
                    </Box>
                  }
                >
                  <Chip
                    label={`Health: ${health.health}`}
                    size="small"
                    color={health.health >= 70 ? "success" : health.health >= 40 ? "warning" : "error"}
                    variant="outlined"
                    sx={{ fontWeight: "bold" }}
                  />
                </Tooltip>
              )}
            </Box>

            {project.human_description && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {project.human_description}
              </Typography>
            )}

            {/* Metadata pills */}
            <Box sx={{ display: "flex", gap: 1, mt: 1.5, flexWrap: "wrap", alignItems: "center" }}>
              {project.llm && (
                <Chip icon={<Psychology />} label={project.llm} size="small" variant="outlined" />
              )}
              {project.options?.fallback_llm && (
                <Chip label={`Fallback: ${project.options.fallback_llm}`} size="small" variant="outlined" />
              )}
              {project.team && (
                <Chip icon={<Groups />} label={project.team.name} size="small" variant="outlined" />
              )}
              {project.guard && (
                <Chip icon={<Shield />} label={`Guard: ${project.guard}`} size="small" variant="outlined" color="warning" />
              )}
              {project.options?.guard_output && (
                <Chip icon={<Shield />} label={`Output Guard: ${project.options.guard_output}`} size="small" variant="outlined" color="warning" />
              )}
              {project.options?.cache && (
                <Chip icon={<Cached />} label="Cache" size="small" variant="outlined" color="info" />
              )}
              {project.options?.rate_limit && (
                <Chip icon={<Speed />} label={`${project.options.rate_limit} req/min`} size="small" variant="outlined" />
              )}
              {project.public && (
                <Chip label="Shared" size="small" color="info" />
              )}
            </Box>

            {/* System prompt preview */}
            {project.system && project.type !== "block" && (
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  mt: 1,
                  display: "-webkit-box",
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  fontStyle: "italic",
                }}
              >
                {project.system}
              </Typography>
            )}

            {/* Users */}
            {project.users && project.users.length > 0 && (
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 1.5 }}>
                <Typography variant="caption" color="text.secondary" sx={{ mr: 0.5 }}>Users:</Typography>
                {project.users.slice(0, 5).map((u, i) => (
                  <Tooltip key={u.username || i} title={u.username}>
                    <Avatar src={"https://www.gravatar.com/avatar/" + sha256(u.username || "")} sx={{ width: 24, height: 24 }} />
                  </Tooltip>
                ))}
                {project.users.length > 5 && (
                  <Chip label={`+${project.users.length - 5}`} size="small" />
                )}
              </Box>
            )}
          </Box>
        </Box>

        {/* Action Toolbar */}
        <ActionBar>
          <Tooltip title="Edit">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/edit")}>
              <Edit fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Playground">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/playground")}>
              <SportsEsports fontSize="small" />
            </IconButton>
          </Tooltip>
          {project.type === "block" && (
            <Tooltip title="IDE">
              <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/ide")}>
                <ViewInAr fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title="Evals">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/evals")}>
              <Science fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Guards">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/guards")}>
              <Security fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Logs">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/logs")}>
              <Article fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="API">
            <IconButton size="small" onClick={() => navigate("/project/" + project.id + "/api")}>
              <Code fontSize="small" />
            </IconButton>
          </Tooltip>

          <Box sx={{ flex: 1 }} />

          {project.options?.cache && (
            <Tooltip title="Clear Cache">
              <IconButton
                size="small"
                color="warning"
                onClick={() => {
                  api.delete("/projects/" + project.id + "/cache", auth.user.token).catch(() => {});
                }}
              >
                <ClearAll fontSize="small" />
              </IconButton>
            </Tooltip>
          )}
          <Tooltip title="Clone">
            <IconButton size="small" onClick={() => { setCloneName(project.name + "-copy"); setCloneOpen(true); }}>
              <ContentCopy fontSize="small" />
            </IconButton>
          </Tooltip>
          <Tooltip title="Delete">
            <IconButton size="small" color="error" onClick={handleDelete}>
              <Delete fontSize="small" />
            </IconButton>
          </Tooltip>
        </ActionBar>
      </HeroCard>

      {/* Project Details */}
      {(() => {
        const showConfig = project.type !== "block";
        const showSecurity = true;
        const showRag = project.type === "rag";
        const showAgent = project.type === "agent";
        const showIntegrations = !!(project.options?.telegram_token || project.options?.slack_bot_token);
        if (!(showConfig || showSecurity || showRag || showAgent || showIntegrations)) return null;
        return (
          <Card elevation={1} sx={{ p: 2.5, mb: 2 }}>
            <Stack divider={<Divider />} spacing={2}>
              {showConfig && (
                <Box>
                  <SectionTitle><Settings fontSize="small" /> Configuration</SectionTitle>
                  <Grid container spacing={2}>
                    <DetailItem label="Logging">
                      <Chip label={project.options?.logging !== false ? "Enabled" : "Disabled"} size="small"
                        color={project.options?.logging !== false ? "success" : "default"} variant="outlined" />
                    </DetailItem>
                    {project.options?.fallback_llm && (
                      <DetailItem label="Fallback LLM">
                        <Typography variant="body2" fontFamily="monospace">{project.options.fallback_llm}</Typography>
                      </DetailItem>
                    )}
                    {project.options?.cache && (
                      <DetailItem label="Cache Threshold">
                        <Typography variant="body2">{project.options.cache_threshold ?? 0.85}</Typography>
                      </DetailItem>
                    )}
                    {project.options?.rate_limit && (
                      <DetailItem label="Rate Limit">
                        <Typography variant="body2">{project.options.rate_limit} req/min</Typography>
                      </DetailItem>
                    )}
                    {project.default_prompt && (
                      <Grid item xs={12}>
                        <Typography variant="caption" color="text.secondary" display="block">Default Prompt</Typography>
                        <Typography variant="body2" sx={{
                          display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                          overflow: "hidden", fontStyle: "italic", color: "text.secondary", mt: 0.5,
                        }}>
                          {project.default_prompt}
                        </Typography>
                      </Grid>
                    )}
                  </Grid>
                </Box>
              )}

              {showSecurity && (
                <Box>
                  <SectionTitle><Shield fontSize="small" /> Security</SectionTitle>
                  <Grid container spacing={2}>
                    <DetailItem label="Input Guard">
                      {project.guard ? (
                        <Chip label={project.guard} size="small" color="warning" variant="outlined" />
                      ) : (
                        <Typography variant="body2" color="text.secondary">Disabled</Typography>
                      )}
                    </DetailItem>
                    <DetailItem label="Output Guard">
                      {project.options?.guard_output ? (
                        <Chip label={project.options.guard_output} size="small" color="warning" variant="outlined" />
                      ) : (
                        <Typography variant="body2" color="text.secondary">Disabled</Typography>
                      )}
                    </DetailItem>
                    {project.options?.guard_mode && (project.guard || project.options?.guard_output) && (
                      <DetailItem label="Guard Mode">
                        <Chip label={project.options.guard_mode === "warn" ? "Warn" : "Block"} size="small"
                          color={project.options.guard_mode === "warn" ? "warning" : "error"} variant="outlined" />
                      </DetailItem>
                    )}
                    {project.censorship && (
                      <Grid item xs={12} sm={8}>
                        <Typography variant="caption" color="text.secondary" display="block">Censorship Message</Typography>
                        <Typography variant="body2" sx={{
                          display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical",
                          overflow: "hidden", fontStyle: "italic", bgcolor: "action.hover",
                          p: 1, borderRadius: 1, mt: 0.5,
                        }}>
                          {project.censorship}
                        </Typography>
                      </Grid>
                    )}
                  </Grid>
                </Box>
              )}

              {showRag && (
                <Box>
                  <SectionTitle><Storage fontSize="small" /> RAG Settings</SectionTitle>
                  <Grid container spacing={2}>
                    <DetailItem label="Documents">
                      <Typography variant="body2" fontWeight="bold">{project.chunks ?? 0}</Typography>
                    </DetailItem>
                    {project.embeddings && (
                      <DetailItem label="Embeddings">
                        <Typography variant="body2" fontFamily="monospace">{project.embeddings}</Typography>
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
                        <Typography variant="body2">{project.options.cache_threshold ?? 0.85}</Typography>
                      </DetailItem>
                    )}
                    {project.options?.connection && (
                      <DetailItem label="SQL Connection">
                        <Chip label="Configured" size="small" color="info" variant="outlined" />
                      </DetailItem>
                    )}
                    {project.options?.tables && (
                      <DetailItem label="SQL Tables">
                        <Typography variant="body2" fontFamily="monospace">{project.options.tables}</Typography>
                      </DetailItem>
                    )}
                  </Grid>
                </Box>
              )}

              {showAgent && (
                <Box>
                  <SectionTitle><Build fontSize="small" /> Agent Settings</SectionTitle>
                  <Grid container spacing={2}>
                    {project.options?.tools && (
                      <Grid item xs={12}>
                        <Typography variant="caption" color="text.secondary" display="block">Tools</Typography>
                        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
                          {project.options.tools.split(",").filter(Boolean).map((t) => (
                            <Chip key={t.trim()} label={t.trim()} size="small" variant="outlined" />
                          ))}
                        </Box>
                      </Grid>
                    )}
                    <DetailItem label="Max Iterations">
                      <Typography variant="body2">{project.options?.max_iterations ?? 10}</Typography>
                    </DetailItem>
                    {project.options?.mcp_servers && project.options.mcp_servers.length > 0 && (
                      <Grid item xs={12}>
                        <Typography variant="caption" color="text.secondary" display="block" gutterBottom>MCP Servers</Typography>
                        {mcpLoading ? (
                          <Box display="flex" justifyContent="center" my={2}>
                            <CircularProgress size={24} />
                          </Box>
                        ) : (
                          project.options.mcp_servers.map((server, index) => (
                            <Accordion key={index} variant="outlined" disableGutters sx={{ mb: 1, "&:before": { display: "none" } }}>
                              <AccordionSummary expandIcon={<ExpandMore />}>
                                <Typography variant="body2">{server.host}</Typography>
                              </AccordionSummary>
                              <AccordionDetails>
                                {server.tools ? (
                                  <Box sx={{ mb: 1.5 }}>
                                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>Configured Tools</Typography>
                                    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                                      {server.tools.split(",").filter(Boolean).map((t) => (
                                        <Chip key={t.trim()} label={t.trim()} size="small" variant="outlined" />
                                      ))}
                                    </Box>
                                  </Box>
                                ) : (
                                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>All tools available from server</Typography>
                                )}
                                {mcpTools[server.host]?.tools && (
                                  <Box>
                                    <Typography variant="caption" color="text.secondary" display="block" gutterBottom>Available Tools</Typography>
                                    {mcpTools[server.host].tools.map((tool, i) => (
                                      <Accordion key={i} variant="outlined" disableGutters sx={{ mb: 0.5, "&:before": { display: "none" } }}>
                                        <AccordionSummary expandIcon={<ExpandMore fontSize="small" />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.5 } }}>
                                          <Typography variant="body2">{tool.name}</Typography>
                                        </AccordionSummary>
                                        <AccordionDetails sx={{ pt: 0 }}>
                                          <Typography variant="caption" color="text.secondary">{tool.description}</Typography>
                                        </AccordionDetails>
                                      </Accordion>
                                    ))}
                                  </Box>
                                )}
                                {mcpTools[server.host]?.error && (
                                  <Typography variant="body2" color="error">
                                    {mcpTools[server.host].message || "Error connecting to server"}
                                  </Typography>
                                )}
                              </AccordionDetails>
                            </Accordion>
                          ))
                        )}
                      </Grid>
                    )}
                    {project.options?.function_agent && (
                      <DetailItem label="Agent Mode">
                        <Chip label="Function Agent" size="small" color="info" variant="outlined" />
                      </DetailItem>
                    )}
                  </Grid>
                </Box>
              )}

              {showIntegrations && (
                <Box>
                  <SectionTitle><Chat fontSize="small" /> Integrations</SectionTitle>
                  <Grid container spacing={2}>
                    {project.options?.telegram_token && (
                      <DetailItem label="Telegram">
                        <Chip label="Connected" size="small" color="success" variant="outlined" />
                      </DetailItem>
                    )}
                    {project.options?.slack_bot_token && (
                      <DetailItem label="Slack">
                        <Chip label="Connected" size="small" color="success" variant="outlined" />
                      </DetailItem>
                    )}
                  </Grid>
                </Box>
              )}
            </Stack>
          </Card>
        );
      })()}

      {/* Clone dialog */}
      <Dialog open={cloneOpen} onClose={() => setCloneOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Clone Project</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense"
            label="New project name"
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            helperText="Settings, eval datasets, and prompt versions will be cloned."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloneOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleClone} disabled={!cloneName.trim()}>Clone</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
