import { SmartToy } from "@mui/icons-material";
import {
  Card,
  Table,
  styled,
  Divider,
  TableRow,
  TableBody,
  TableCell,
  Box,
  Autocomplete,
  TextField,
  Typography,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  CircularProgress
} from "@mui/material";
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { useState, useEffect } from "react";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

const ServerTools = styled(Box)({
  marginBottom: "16px"
});

export default function ProjectAgent({ project, projects }) {
  const auth = useAuth();
  const [tools, setTools] = useState([]);
  const [mcpTools, setMcpTools] = useState({});
  const [loading, setLoading] = useState(false);

  const fetchTools = () => {
    return api.get("/tools/agent", auth.user.token)
      .then((d) => {
        setTools(d)
      }).catch(() => {});
  }

  const fetchMcpTools = () => {
    if (!project || !project.id) return;

    setLoading(true);
    return api.get(`/projects/${project.id}/tools`, auth.user.token)
      .then((data) => {
        setMcpTools(data.mcp_servers || {});
      })
      .catch(() => {})
      .finally(() => {
        setLoading(false);
      });
  }

  useEffect(() => {
    fetchTools();
    if (project && project.options && project.options.mcp_servers && project.options.mcp_servers.length > 0) {
      fetchMcpTools();
    }
  }, [project]);

  return (
    <Card elevation={3}>
      <FlexBox>
        <SmartToy sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>
          Agent
        </H4>
      </FlexBox>
      <Divider />

      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Tools</TableCell>
            <TableCell>
              <Autocomplete
                multiple
                disabled
                id="tags-standard"
                options={(project.options.tools || "").split(",")}
                getOptionLabel={(option) => option}
                defaultValue={(project.options.tools || "").split(",")}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    fullWidth
                    variant="standard"
                    label=""
                    placeholder=""
                  />
                )}
              />
            </TableCell>
          </TableRow>
          
          {project.options && project.options.mcp_servers && project.options.mcp_servers.length > 0 && (
            <TableRow>
              <TableCell sx={{ pl: 2 }}>MCP Servers</TableCell>
              <TableCell>
                {loading ? (
                  <Box display="flex" justifyContent="center" my={2}>
                    <CircularProgress size={24} />
                  </Box>
                ) : (
                  project.options.mcp_servers.map((server, index) => (
                    <Accordion key={index} sx={{ mb: 1 }}>
                      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                        <Typography>{server.host}</Typography>
                      </AccordionSummary>
                      <AccordionDetails>
                        <ServerTools>
                          <Typography variant="subtitle2" color="textSecondary">Configured Tools:</Typography>
                          {server.tools ? (
                            <Autocomplete
                              multiple
                              disabled
                              options={server.tools.split(",")}
                              getOptionLabel={(option) => option}
                              defaultValue={server.tools.split(",")}
                              renderInput={(params) => (
                                <TextField
                                  {...params}
                                  fullWidth
                                  size="small"
                                  variant="outlined"
                                  sx={{ mt: 1 }}
                                />
                              )}
                            />
                          ) : (
                            <Typography variant="body2">All tools available from server</Typography>
                          )}
                        </ServerTools>
                        
                        {mcpTools[server.host] && mcpTools[server.host].tools && (
                          <ServerTools>
                            <Typography variant="subtitle2" color="textSecondary">Available Tools:</Typography>
                            <Box mt={1}>
                              {mcpTools[server.host].tools.map((tool, toolIndex) => (
                                <Accordion key={toolIndex} sx={{ mb: 1 }}>
                                  <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                                    <Typography>{tool.name}</Typography>
                                  </AccordionSummary>
                                  <AccordionDetails>
                                    <Typography variant="body2">{tool.description}</Typography>
                                  </AccordionDetails>
                                </Accordion>
                              ))}
                            </Box>
                          </ServerTools>
                        )}
                        
                        {mcpTools[server.host] && mcpTools[server.host].error && (
                          <Typography color="error">
                            {mcpTools[server.host].message || "Error connecting to server"}
                          </Typography>
                        )}
                      </AccordionDetails>
                    </Accordion>
                  ))
                )}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Card>
  );
}
