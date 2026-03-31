import { SmartToy } from "@mui/icons-material";
import {
  Card, Chip, Grid, Typography, styled, Box,
  Accordion, AccordionSummary, AccordionDetails, CircularProgress,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useState, useEffect } from "react";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const SectionTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  fontSize: "0.9rem",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.5),
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1),
}));

export default function ProjectAgent({ project }) {
  const auth = useAuth();
  const [mcpTools, setMcpTools] = useState({});
  const [loading, setLoading] = useState(false);

  const fetchMcpTools = () => {
    if (!project || !project.id) return;
    setLoading(true);
    return api.get(`/projects/${project.id}/tools`, auth.user.token)
      .then((data) => setMcpTools(data.mcp_servers || {}))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    if (project && project.options && project.options.mcp_servers && project.options.mcp_servers.length > 0) {
      fetchMcpTools();
    }
  }, [project]);

  const toolsList = (project.options?.tools || "").split(",").filter(Boolean);

  return (
    <Card elevation={1} sx={{ p: 2.5 }}>
      <SectionTitle><SmartToy fontSize="small" /> Agent</SectionTitle>

      {/* Tools */}
      {toolsList.length > 0 && (
        <Box sx={{ mb: 2 }}>
          <Typography variant="caption" color="text.secondary" display="block" gutterBottom>Tools</Typography>
          <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
            {toolsList.map((t) => (
              <Chip key={t.trim()} label={t.trim()} size="small" variant="outlined" />
            ))}
          </Box>
        </Box>
      )}

      {/* MCP Servers */}
      {project.options?.mcp_servers && project.options.mcp_servers.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" display="block" gutterBottom>MCP Servers</Typography>
          {loading ? (
            <Box display="flex" justifyContent="center" my={2}>
              <CircularProgress size={24} />
            </Box>
          ) : (
            project.options.mcp_servers.map((server, index) => (
              <Accordion key={index} variant="outlined" disableGutters sx={{ mb: 1, "&:before": { display: "none" } }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Typography variant="body2">{server.host}</Typography>
                </AccordionSummary>
                <AccordionDetails>
                  {server.tools && (
                    <Box sx={{ mb: 1.5 }}>
                      <Typography variant="caption" color="text.secondary" display="block" gutterBottom>Configured Tools</Typography>
                      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                        {server.tools.split(",").filter(Boolean).map((t) => (
                          <Chip key={t.trim()} label={t.trim()} size="small" variant="outlined" />
                        ))}
                      </Box>
                    </Box>
                  )}
                  {!server.tools && (
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>All tools available from server</Typography>
                  )}

                  {mcpTools[server.host] && mcpTools[server.host].tools && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" display="block" gutterBottom>Available Tools</Typography>
                      {mcpTools[server.host].tools.map((tool, toolIndex) => (
                        <Accordion key={toolIndex} variant="outlined" disableGutters sx={{ mb: 0.5, "&:before": { display: "none" } }}>
                          <AccordionSummary expandIcon={<ExpandMoreIcon fontSize="small" />} sx={{ minHeight: 36, "& .MuiAccordionSummary-content": { my: 0.5 } }}>
                            <Typography variant="body2">{tool.name}</Typography>
                          </AccordionSummary>
                          <AccordionDetails sx={{ pt: 0 }}>
                            <Typography variant="caption" color="text.secondary">{tool.description}</Typography>
                          </AccordionDetails>
                        </Accordion>
                      ))}
                    </Box>
                  )}

                  {mcpTools[server.host] && mcpTools[server.host].error && (
                    <Typography variant="body2" color="error">
                      {mcpTools[server.host].message || "Error connecting to server"}
                    </Typography>
                  )}
                </AccordionDetails>
              </Accordion>
            ))
          )}
        </Box>
      )}

      {toolsList.length === 0 && (!project.options?.mcp_servers || project.options.mcp_servers.length === 0) && (
        <Typography variant="body2" color="text.secondary">No tools configured</Typography>
      )}
    </Card>
  );
}
