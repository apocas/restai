import { useState, useEffect } from "react";
import {
  Box, Card, Chip, CircularProgress, Divider, Typography, styled,
  Accordion, AccordionSummary, AccordionDetails,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import BuildIcon from "@mui/icons-material/Build";
import DnsIcon from "@mui/icons-material/Dns";
import HandymanIcon from "@mui/icons-material/Handyman";
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

export default function ProjectInfoTools({ project }) {
  const [customTools, setCustomTools] = useState([]);
  const [loading, setLoading] = useState(true);
  const auth = useAuth();

  useEffect(() => {
    if (!project?.id) return;
    setLoading(true);
    api.get(`/projects/${project.id}/custom-tools`, auth.user.token)
      .then((d) => setCustomTools(d.tools || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [project?.id]);

  const builtinTools = (project.options?.tools || "").split(",").map((t) => t.trim()).filter(Boolean);

  if (loading) return <Box sx={{ textAlign: "center", py: 4 }}><CircularProgress size={24} /></Box>;

  return (
    <Card elevation={1} sx={{ p: 3 }}>
      <SectionTitle><HandymanIcon fontSize="small" /> Built-in Tools</SectionTitle>
      {builtinTools.length === 0 ? (
        <Typography variant="body2" color="textSecondary" sx={{ mb: 2 }}>
          No built-in tools configured.
        </Typography>
      ) : (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mb: 2 }}>
          {builtinTools.map((t) => (
            <Chip key={t} label={t} size="small" variant="outlined" sx={{ fontFamily: "monospace" }} />
          ))}
        </Box>
      )}

      {/* MCP Servers */}
      {project.options?.mcp_servers && project.options.mcp_servers.length > 0 && (
        <>
          <Divider sx={{ my: 2 }} />
          <SectionTitle><DnsIcon fontSize="small" /> MCP Servers</SectionTitle>
          {project.options.mcp_servers.map((srv, i) => (
            <Card key={i} variant="outlined" sx={{ p: 1.5, mb: 1, borderRadius: 1 }}>
              <Typography variant="body2" fontWeight={600} sx={{ fontFamily: "monospace" }}>
                {srv.host}
              </Typography>
              {srv.args && srv.args.length > 0 && (
                <Typography variant="caption" color="textSecondary" sx={{ display: "block" }}>
                  Args: {srv.args.join(" ")}
                </Typography>
              )}
              {srv.tools && (
                <Typography variant="caption" color="textSecondary" sx={{ display: "block" }}>
                  Tools: {srv.tools}
                </Typography>
              )}
            </Card>
          ))}
        </>
      )}

      {/* Agent-created tools */}
      {customTools.length > 0 && (
        <>
          <Divider sx={{ my: 2 }} />
          <SectionTitle><BuildIcon fontSize="small" /> Agent-Created Tools</SectionTitle>
          {customTools.map((tool) => (
            <Accordion key={tool.id} disableGutters variant="outlined" sx={{ mb: 1, borderRadius: 1, "&:before": { display: "none" }, opacity: tool.enabled === false ? 0.5 : 1 }}>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1 }}>
                  <Typography variant="body2" fontWeight={600} sx={{ fontFamily: "monospace" }}>
                    {tool.name}
                  </Typography>
                  <Chip
                    label={tool.enabled === false ? "Disabled" : "Enabled"}
                    size="small"
                    color={tool.enabled === false ? "default" : "success"}
                    variant="outlined"
                    sx={{ height: 20, fontSize: "0.68rem" }}
                  />
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="body2" color="textSecondary" sx={{ mb: 1 }}>
                  {tool.description}
                </Typography>
                <Typography variant="caption" color="textSecondary">
                  Created: {tool.created_at ? new Date(tool.created_at).toLocaleString() : "—"}
                </Typography>
              </AccordionDetails>
            </Accordion>
          ))}
        </>
      )}

      {builtinTools.length === 0 && customTools.length === 0 && (
        <Typography variant="body2" color="textSecondary" sx={{ textAlign: "center", py: 2 }}>
          No tools configured for this project.
        </Typography>
      )}
    </Card>
  );
}
