import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Avatar,
  Box,
  Card,
  Chip,
  CircularProgress,
  Divider,
  Grid,
  Stack,
  Tooltip,
  Typography,
  styled,
} from "@mui/material";
import {
  Build,
  Cached,
  Chat,
  ExpandMore,
  Groups,
  Person,
  Psychology,
  Settings,
  Shield,
  Speed,
} from "@mui/icons-material";
import sha256 from "crypto-js/sha256";
import ProjectBlock from "./ProjectBlock";

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

const MetaItem = styled(Box)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  gap: 4,
  color: theme.palette.text.secondary,
  fontSize: "0.85rem",
}));

const TYPE_COLORS = {
  inference: "primary",
  rag: "success",
  agent: "warning",
  block: "default",
};

export default function ProjectInfoGeneral({ project, info, health, mcpTools, mcpLoading }) {
  const showConfig = project.type !== "block";
  const showAgent = project.type === "agent";
  const showIntegrations = !!(project.options?.telegram_token || project.options?.slack_bot_token);

  return (
    <Grid container spacing={3}>
      {/* Metadata pills */}
      <Grid item xs={12}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}>
            <Chip label={project.type} size="small" color={TYPE_COLORS[project.type] || "default"} />
            {project.llm && (
              <Chip icon={<Psychology />} label={project.llm} size="small" variant="outlined" />
            )}
            {project.team && (
              <Chip icon={<Groups />} label={project.team.name} size="small" variant="outlined" />
            )}
            {project.options?.cache && (
              <Chip icon={<Cached />} label="Cache" size="small" variant="outlined" color="info" />
            )}
            {project.guard && (
              <Chip icon={<Shield />} label={`Guard: ${project.guard}`} size="small" variant="outlined" color="warning" />
            )}
            {project.options?.guard_output && (
              <Chip icon={<Shield />} label={`Output Guard: ${project.options.guard_output}`} size="small" variant="outlined" color="warning" />
            )}
            {project.options?.rate_limit && (
              <Chip icon={<Speed />} label={`${project.options.rate_limit} req/min`} size="small" variant="outlined" />
            )}
            {project.creator_username && (
              <Chip icon={<Person />} label={`Owner: ${project.creator_username}`} size="small" variant="outlined" />
            )}
            {project.public && (
              <Chip label="Shared" size="small" color="info" />
            )}
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
        </Card>
      </Grid>

      {/* System prompt preview */}
      {project.system && project.type !== "block" && (
        <Grid item xs={12}>
          <Card elevation={1} sx={{ p: 2.5 }}>
            <SectionTitle>System Prompt</SectionTitle>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                display: "-webkit-box",
                WebkitLineClamp: 4,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                fontStyle: "italic",
                bgcolor: "action.hover",
                p: 1.5,
                borderRadius: 1,
              }}
            >
              {project.system}
            </Typography>
          </Card>
        </Grid>
      )}

      {/* Users with access */}
      {project.users && project.users.length > 0 && (
        <Grid item xs={12}>
          <Card elevation={1} sx={{ p: 2.5 }}>
            <SectionTitle>Users with Access</SectionTitle>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap" }}>
              {project.users.slice(0, 10).map((u, i) => {
                const username = typeof u === "string" ? u : u.username;
                return (
                  <Tooltip key={username || i} title={username} placement="top" arrow>
                    <Box sx={{ display: "inline-flex" }}>
                      <Avatar
                        src={"https://www.gravatar.com/avatar/" + sha256(username || "")}
                        sx={{ width: 32, height: 32 }}
                      />
                    </Box>
                  </Tooltip>
                );
              })}
              {project.users.length > 10 && (
                <Chip label={`+${project.users.length - 10}`} size="small" />
              )}
            </Box>
          </Card>
        </Grid>
      )}

      {/* Configuration */}
      {showConfig && (
        <Grid item xs={12}>
          <Card elevation={1} sx={{ p: 2.5 }}>
            <SectionTitle><Settings fontSize="small" /> Configuration</SectionTitle>
            <Grid container spacing={2}>
              <DetailItem label="Logging">
                <Chip
                  label={project.options?.logging !== false ? "Enabled" : "Disabled"}
                  size="small"
                  color={project.options?.logging !== false ? "success" : "default"}
                  variant="outlined"
                />
              </DetailItem>
              {project.options?.fallback_llm && (
                <DetailItem label="Fallback LLM">
                  <Typography variant="body2" fontFamily="monospace">
                    {project.options.fallback_llm}
                  </Typography>
                </DetailItem>
              )}
              {project.options?.cache && (
                <DetailItem label="Cache Threshold">
                  <Typography variant="body2">
                    {project.options.cache_threshold ?? 0.85}
                  </Typography>
                </DetailItem>
              )}
              {project.options?.rate_limit && (
                <DetailItem label="Rate Limit">
                  <Typography variant="body2">
                    {project.options.rate_limit} req/min
                  </Typography>
                </DetailItem>
              )}
              {project.default_prompt && (
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    Default Prompt
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      display: "-webkit-box",
                      WebkitLineClamp: 2,
                      WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                      fontStyle: "italic",
                      color: "text.secondary",
                      mt: 0.5,
                    }}
                  >
                    {project.default_prompt}
                  </Typography>
                </Grid>
              )}
            </Grid>
          </Card>
        </Grid>
      )}

      {/* Integrations */}
      {showIntegrations && (
        <Grid item xs={12}>
          <Card elevation={1} sx={{ p: 2.5 }}>
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
          </Card>
        </Grid>
      )}

      {/* Block config */}
      {project.type === "block" && (
        <Grid item xs={12}>
          <ProjectBlock project={project} />
        </Grid>
      )}

      {/* Agent settings */}
      {showAgent && (
        <Grid item xs={12}>
          <Card elevation={1} sx={{ p: 2.5 }}>
            <SectionTitle><Build fontSize="small" /> Agent Settings</SectionTitle>
            <Grid container spacing={2}>
              {project.options?.tools && (
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary" display="block">
                    Tools
                  </Typography>
                  <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
                    {project.options.tools
                      .split(",")
                      .filter(Boolean)
                      .map((t) => (
                        <Chip key={t.trim()} label={t.trim()} size="small" variant="outlined" />
                      ))}
                  </Box>
                </Grid>
              )}
              <DetailItem label="Max Iterations">
                <Typography variant="body2">
                  {project.options?.max_iterations ?? 10}
                </Typography>
              </DetailItem>
              {project.options?.mcp_servers && project.options.mcp_servers.length > 0 && (
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                    MCP Servers
                  </Typography>
                  {mcpLoading ? (
                    <Box display="flex" justifyContent="center" my={2}>
                      <CircularProgress size={24} />
                    </Box>
                  ) : (
                    project.options.mcp_servers.map((server, index) => (
                      <Accordion
                        key={index}
                        variant="outlined"
                        disableGutters
                        sx={{ mb: 1, "&:before": { display: "none" } }}
                      >
                        <AccordionSummary expandIcon={<ExpandMore />}>
                          <Typography variant="body2">{server.host}</Typography>
                        </AccordionSummary>
                        <AccordionDetails>
                          {server.tools ? (
                            <Box sx={{ mb: 1.5 }}>
                              <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                Configured Tools
                              </Typography>
                              <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                                {server.tools
                                  .split(",")
                                  .filter(Boolean)
                                  .map((t) => (
                                    <Chip key={t.trim()} label={t.trim()} size="small" variant="outlined" />
                                  ))}
                              </Box>
                            </Box>
                          ) : (
                            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                              All tools available from server
                            </Typography>
                          )}
                          {mcpTools?.[server.host]?.tools && (
                            <Box>
                              <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                Available Tools
                              </Typography>
                              {mcpTools?.[server.host]?.tools?.map((tool, i) => (
                                <Accordion
                                  key={i}
                                  variant="outlined"
                                  disableGutters
                                  sx={{ mb: 0.5, "&:before": { display: "none" } }}
                                >
                                  <AccordionSummary
                                    expandIcon={<ExpandMore fontSize="small" />}
                                    sx={{
                                      minHeight: 36,
                                      "& .MuiAccordionSummary-content": { my: 0.5 },
                                    }}
                                  >
                                    <Typography variant="body2">{tool.name}</Typography>
                                  </AccordionSummary>
                                  <AccordionDetails sx={{ pt: 0 }}>
                                    <Typography variant="caption" color="text.secondary">
                                      {tool.description}
                                    </Typography>
                                  </AccordionDetails>
                                </Accordion>
                              ))}
                            </Box>
                          )}
                          {mcpTools?.[server.host]?.error && (
                            <Typography variant="body2" color="error">
                              {mcpTools?.[server.host]?.message || "Error connecting to server"}
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
          </Card>
        </Grid>
      )}
    </Grid>
  );
}
