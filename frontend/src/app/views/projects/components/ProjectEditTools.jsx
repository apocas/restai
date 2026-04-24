import {
  Grid, TextField, Button, Autocomplete, Typography, IconButton, Divider, Box,
  CircularProgress, MenuItem, Chip, Accordion, AccordionSummary, AccordionDetails,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import BuildIcon from "@mui/icons-material/Build";
import { Fragment, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { json as jsonLang } from "@codemirror/lang-json";

function parseHeadersText(text) {
  const parsed = {};
  if (!text) return parsed;
  text.split("\n").forEach(line => {
    const colonIdx = line.indexOf(":");
    if (colonIdx > 0) {
      const key = line.substring(0, colonIdx).trim();
      const value = line.substring(colonIdx + 1).trim();
      if (key) parsed[key] = value;
    }
  });
  return parsed;
}

function GatewayServices({ gateway, onAdd }) {
  const [selected, setSelected] = useState({});
  const services = gateway.services || [];
  const toggleService = (svc) => setSelected(prev => ({ ...prev, [svc]: !prev[svc] }));
  const selectedList = services.filter(s => selected[s]);

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="subtitle2" gutterBottom>
        MCP Gateway: {gateway.name || "Unknown"}
      </Typography>
      {gateway.description && (
        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
          {gateway.description}
        </Typography>
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
        Select services to add:
      </Typography>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, mb: 1.5 }}>
        {services.map((svc) => (
          <Box
            key={svc}
            onClick={() => toggleService(svc)}
            sx={{
              display: "flex", alignItems: "center", gap: 1,
              p: 1, borderRadius: 1, cursor: "pointer",
              border: "1px solid", borderColor: selected[svc] ? "primary.main" : "divider",
              bgcolor: selected[svc] ? "action.selected" : "transparent",
              "&:hover": { bgcolor: "action.hover" },
            }}
          >
            <input type="checkbox" checked={!!selected[svc]} readOnly style={{ pointerEvents: "none" }} />
            <Typography variant="body2" fontFamily="monospace">{svc}</Typography>
          </Box>
        ))}
      </Box>
      <Button
        variant="contained" size="small"
        disabled={selectedList.length === 0}
        onClick={() => onAdd(selectedList)}
      >
        Add {selectedList.length} Service{selectedList.length !== 1 ? "s" : ""}
      </Button>
    </Box>
  );
}

function AgentCreatedTools({ project }) {
  const [customTools, setCustomTools] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editOpen, setEditOpen] = useState(false);
  const [editTool, setEditTool] = useState(null);
  const [editDesc, setEditDesc] = useState("");
  const [editParams, setEditParams] = useState("");
  const [editCode, setEditCode] = useState("");
  const [saving, setSaving] = useState(false);
  const auth = useAuth();
  const theme = useTheme();

  const fetchTools = () => {
    if (!project?.id) return;
    setLoading(true);
    api.get(`/projects/${project.id}/custom-tools`, auth.user.token)
      .then((d) => setCustomTools(d.tools || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchTools();
  }, [project?.id]);

  const handleDelete = (name) => {
    if (!window.confirm(`Delete tool "${name}"? The agent won't be able to use it anymore.`)) return;
    api.delete(`/projects/${project.id}/custom-tools/${name}`, auth.user.token)
      .then(() => {
        toast.success(`Tool "${name}" deleted`);
        fetchTools();
      })
      .catch(() => {});
  };

  const handleToggle = (name) => {
    api.patch(`/projects/${project.id}/custom-tools/${name}`, {}, auth.user.token)
      .then((d) => {
        toast.success(`Tool "${name}" ${d.enabled ? "enabled" : "disabled"}`);
        fetchTools();
      })
      .catch(() => {});
  };

  const handleEditOpen = (tool) => {
    setEditTool(tool);
    setEditDesc(tool.description || "");
    let params = tool.parameters || "";
    try { params = JSON.stringify(JSON.parse(params), null, 2); } catch {}
    setEditParams(params);
    setEditCode(tool.code || "");
    setEditOpen(true);
  };

  const handleEditSave = () => {
    try { JSON.parse(editParams); } catch {
      toast.error("Invalid JSON in parameters");
      return;
    }
    if (editCode.length > 10240) {
      toast.error("Code exceeds 10KB limit");
      return;
    }
    setSaving(true);
    api.put(`/projects/${project.id}/custom-tools/${editTool.name}`, {
      description: editDesc,
      parameters: editParams,
      code: editCode,
    }, auth.user.token)
      .then((d) => {
        toast.success(`Tool "${editTool.name}" updated`);
        if (d.warning) toast.warn(d.warning);
        setEditOpen(false);
        fetchTools();
      })
      .catch(() => {})
      .finally(() => setSaving(false));
  };

  if (loading) return <CircularProgress size={20} />;
  if (customTools.length === 0) return null;

  return (
    <Box>
      <Divider sx={{ my: 2 }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1.5 }}>
        <BuildIcon fontSize="small" color="primary" />
        <Typography variant="subtitle1">Agent-Created Tools</Typography>
        <Chip label={customTools.length} size="small" variant="outlined" />
      </Box>
      <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 1.5 }}>
        Tools created by the agent during conversations. These are automatically available in all conversations for this project.
      </Typography>
      {customTools.map((tool) => (
        <Accordion key={tool.id} disableGutters variant="outlined" sx={{ mb: 1, borderRadius: 1, "&:before": { display: "none" }, opacity: tool.enabled === false ? 0.5 : 1 }}>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, flex: 1, mr: 1 }}>
              <Typography variant="body2" fontWeight={600} sx={{ fontFamily: "monospace" }}>
                {tool.name}
              </Typography>
              <Chip
                label={tool.enabled === false ? "Disabled" : "Enabled"}
                size="small"
                color={tool.enabled === false ? "default" : "success"}
                variant="outlined"
                sx={{ fontSize: "0.68rem", height: 20, cursor: "pointer" }}
                onClick={(e) => { e.stopPropagation(); handleToggle(tool.name); }}
              />
              <Typography variant="caption" color="textSecondary" sx={{ flex: 1 }}>
                {tool.description?.substring(0, 80)}{tool.description?.length > 80 ? "..." : ""}
              </Typography>
            </Box>
          </AccordionSummary>
          <AccordionDetails>
            <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 1 }}>
              {tool.description}
            </Typography>
            <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>Parameters</Typography>
            <Box
              sx={{
                p: 1.5, borderRadius: 1, mb: 1.5, fontFamily: "monospace", fontSize: "0.78rem",
                backgroundColor: (t) => t.palette.mode === "dark" ? "#0f0f17" : "#fafafa",
                whiteSpace: "pre-wrap", border: "1px solid", borderColor: "divider",
              }}
            >
              {tool.parameters}
            </Box>
            <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>Code</Typography>
            <Box
              sx={{
                p: 1.5, borderRadius: 1, mb: 1.5, fontFamily: "monospace", fontSize: "0.78rem",
                backgroundColor: (t) => t.palette.mode === "dark" ? "#0f0f17" : "#fafafa",
                whiteSpace: "pre-wrap", border: "1px solid", borderColor: "divider",
                maxHeight: 300, overflow: "auto",
              }}
            >
              {tool.code}
            </Box>
            <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <Typography variant="caption" color="textSecondary">
                Created: {tool.created_at ? new Date(tool.created_at).toLocaleString() : "—"}
              </Typography>
              <Box sx={{ display: "flex", gap: 1 }}>
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<EditIcon />}
                  onClick={() => handleEditOpen(tool)}
                >
                  Edit
                </Button>
                <Button
                  size="small"
                  color="error"
                  variant="outlined"
                  startIcon={<DeleteIcon />}
                  onClick={() => handleDelete(tool.name)}
                >
                  Delete
                </Button>
              </Box>
            </Box>
          </AccordionDetails>
        </Accordion>
      ))}

      <Dialog open={editOpen} onClose={() => !saving && setEditOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle sx={{ fontFamily: "monospace" }}>
          Edit Tool: {editTool?.name}
        </DialogTitle>
        <DialogContent dividers>
          <TextField
            fullWidth
            label="Description"
            multiline
            rows={2}
            value={editDesc}
            onChange={(e) => setEditDesc(e.target.value)}
            sx={{ mb: 2, mt: 1 }}
            inputProps={{ maxLength: 2000 }}
          />

          <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>
            Parameters (JSON Schema)
          </Typography>
          <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, mb: 2, overflow: "hidden" }}>
            <CodeMirror
              value={editParams}
              height="150px"
              extensions={[jsonLang()]}
              theme={theme.palette.mode === "dark" ? "dark" : "light"}
              onChange={(val) => setEditParams(val)}
            />
          </Box>

          <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>
            Code (Python)
          </Typography>
          <Typography variant="caption" color="textSecondary" sx={{ display: "block", mb: 0.5 }}>
            Receives an <code>args</code> dict with the parameters. Print results to stdout.
          </Typography>
          <Box sx={{ border: "1px solid", borderColor: "divider", borderRadius: 1, overflow: "hidden" }}>
            <CodeMirror
              value={editCode}
              height="350px"
              extensions={[python()]}
              theme={theme.palette.mode === "dark" ? "dark" : "light"}
              onChange={(val) => setEditCode(val)}
            />
          </Box>
          <Typography variant="caption" color="textSecondary" sx={{ mt: 0.5, display: "block" }}>
            {editCode.length.toLocaleString()} / 10,240 bytes
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditOpen(false)} disabled={saving}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleEditSave}
            disabled={saving || !editDesc.trim() || !editCode.trim()}
          >
            {saving ? <><CircularProgress size={16} sx={{ mr: 1 }} /> Validating...</> : "Save"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

export default function ProjectEditTools({ state, setState, handleChange, project, mcpServers, setMcpServers, tools, handleAddMcpServer, handleRemoveMcpServer, handleMcpServerFieldChange, handleProbeMcpServer, handleMcpToolsChange, handleAddGatewayServices, isStdioServer }) {
  const { t } = useTranslation();
  return (
    <Grid container spacing={3}>
      <Grid item sm={6} xs={12}>
        <Autocomplete
          multiple
          options={tools.map((tool) => tool.name)}
          getOptionLabel={(option) => option}
          isOptionEqualToValue={(option, value) => option === value}
          onChange={(event, newValue) => {
            setState({
              ...state,
              options: {
                ...state.options,
                tools: newValue.join(",")
              }
            });
          }}
          value={state.options?.tools ? state.options.tools.split(",").filter(tool => tool.trim() !== "") : []}
          renderInput={(params) => (
            <TextField
              {...params}
              fullWidth
              InputLabelProps={{ shrink: true }}
              label={t("nav.tools")}
              variant="outlined"
              helperText="Built-in tools the agent can use during execution (web search, calculator, etc.)"
            />
          )}
        />
      </Grid>
      {project.type === "agent" && (
        <>
        <Grid item sm={3} xs={12}>
          <TextField
            fullWidth
            type="number"
            label="Max Iterations"
            variant="outlined"
            InputLabelProps={{ shrink: true }}
            inputProps={{ min: 1, max: 100 }}
            value={state.options?.max_iterations ?? 10}
            onChange={(e) => setState({
              ...state,
              options: { ...state.options, max_iterations: parseInt(e.target.value, 10) || 10 }
            })}
            helperText="Maximum tool-calling iterations per request"
          />
        </Grid>
        <Grid item sm={9} xs={12}>
          <TextField
            select
            fullWidth
            label="Agent Mode"
            variant="outlined"
            InputLabelProps={{ shrink: true }}
            value={state.options?.agent_mode || "auto"}
            onChange={(e) => setState({
              ...state,
              options: { ...state.options, agent_mode: e.target.value }
            })}
            helperText="How tools are called. 'Auto' tries native function calling and falls back to text-based ReAct on first-turn error. Force 'ReAct' for models without native tool support (e.g. small Ollama models) to skip the failed first attempt."
          >
            <MenuItem value="auto">Auto (native, fall back to ReAct on error)</MenuItem>
            <MenuItem value="function_calling">Function Calling (native only)</MenuItem>
            <MenuItem value="react">ReAct (text-based prompting)</MenuItem>
          </TextField>
        </Grid>
        </>
      )}
      <Grid item sm={12} xs={12}>
        <Divider sx={{ mb: 1 }} />
      </Grid>
      <Grid item sm={12} xs={12}>
        <Typography variant="subtitle1" gutterBottom>{t("projects.edit.tools.mcpServers")}</Typography>
        <Typography variant="caption" color="textSecondary" sx={{ display: 'block', mb: 2 }}>
          Connect to external tool servers using the MCP protocol. Two connection modes are supported:
          <br />
          <strong>HTTP/SSE</strong> — enter a URL (e.g. <code>http://localhost:3001/sse</code> or <code>http://localhost:8000/mcp</code>)
          <br />
          <strong>Stdio</strong> — enter a command (e.g. <code>npx</code>, <code>python</code>, <code>uvx</code>) and its arguments below
        </Typography>
        {mcpServers.map((server, index) => (
          <Box key={index} sx={{ mb: 2, p: 2, border: '1px solid #e0e0e0', borderRadius: 1 }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
              <TextField
                fullWidth
                size="small"
                label={isStdioServer(server.host) ? "Command" : "URL or Command"}
                placeholder="http://localhost:3001/sse or npx"
                value={server.host}
                onChange={(e) => handleMcpServerFieldChange(index, 'host', e.target.value)}
              />
              <Button
                variant="outlined"
                size="small"
                disabled={!server.host.trim() || server.loading}
                onClick={() => handleProbeMcpServer(index)}
                sx={{ minWidth: 80 }}
              >
                {server.loading ? <CircularProgress size={20} /> : t("projects.edit.tools.mcpCheck")}
              </Button>
              <IconButton size="small" onClick={() => handleRemoveMcpServer(index)}>
                <DeleteIcon />
              </IconButton>
            </Box>
            {isStdioServer(server.host) && (
              <Box sx={{ mb: 1 }}>
                <TextField
                  fullWidth
                  size="small"
                  label={t("projects.edit.tools.mcpArguments")}
                  placeholder="-y @modelcontextprotocol/server-filesystem /tmp"
                  helperText="Space-separated arguments passed to the command"
                  value={(server.args || []).join(" ")}
                  onChange={(e) => {
                    const val = e.target.value;
                    handleMcpServerFieldChange(index, 'args', val ? val.split(" ").filter(a => a !== "") : []);
                  }}
                  sx={{ mb: 1 }}
                />
                <TextField
                  fullWidth
                  size="small"
                  label={t("projects.edit.tools.mcpEnvVars")}
                  placeholder="KEY=value ANOTHER=value"
                  helperText="Space-separated KEY=value pairs (e.g. PORT=3001 DEBUG=true)"
                  value={Object.entries(server.env || {}).map(([k, v]) => `${k}=${v}`).join(" ")}
                  onChange={(e) => {
                    const val = e.target.value;
                    const env = {};
                    if (val) {
                      val.split(" ").filter(p => p.includes("=")).forEach(pair => {
                        const eqIdx = pair.indexOf("=");
                        env[pair.substring(0, eqIdx)] = pair.substring(eqIdx + 1);
                      });
                    }
                    handleMcpServerFieldChange(index, 'env', env);
                  }}
                />
              </Box>
            )}
            {!isStdioServer(server.host) && (
              <Box sx={{ mb: 1 }}>
                <TextField
                  fullWidth size="small" multiline rows={2}
                  label={t("projects.edit.tools.mcpHeaders")}
                  placeholder={"Authorization: Bearer token123\nX-API-Key: mykey"}
                  helperText="One header per line in KEY: VALUE format"
                  value={server.headersText ?? ""}
                  onChange={(e) => handleMcpServerFieldChange(index, 'headersText', e.target.value)}
                />
              </Box>
            )}
            {server.error && (
              <Box sx={{ mb: 1, display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="body2" color="error" sx={{ flex: 1 }}>{server.error}</Typography>
                <Button
                  size="small"
                  variant="text"
                  onClick={() => handleProbeMcpServer(index)}
                  disabled={!server.host.trim() || server.loading}
                >
                  Retry
                </Button>
              </Box>
            )}
            {server.gateway && (
              <GatewayServices
                gateway={server.gateway}
                onAdd={(selectedServices) => handleAddGatewayServices(index, selectedServices)}
              />
            )}
            {server.availableTools.length > 0 && !server.gateway && (
              <Autocomplete
                multiple
                freeSolo
                size="small"
                options={server.availableTools.map(t => t.name)}
                value={server.tools ? server.tools.split(",").map(t => t.trim()).filter(t => t !== "") : []}
                onChange={(e, newValue) => handleMcpToolsChange(index, newValue)}
                renderInput={(params) => (
                  <TextField
                    {...params}
                    label="Tools (leave empty for all)"
                    variant="outlined"
                    helperText={`${server.availableTools.length} tool(s) available`}
                  />
                )}
              />
            )}
          </Box>
        ))}
        <Button variant="outlined" size="small" onClick={handleAddMcpServer}>
          Add MCP Server
        </Button>
      </Grid>

      {project?.type === "agent" && (
        <Grid item xs={12}>
          <AgentCreatedTools project={project} />
        </Grid>
      )}
    </Grid>
  );
}
