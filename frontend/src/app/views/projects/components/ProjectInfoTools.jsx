import { useEffect, useRef, useState } from "react";
import {
  Box, Button, CircularProgress, Divider, Snackbar, Alert, Typography,
} from "@mui/material";
import SaveIcon from "@mui/icons-material/Save";
import { Build } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import ProjectEditTools from "./ProjectEditTools";
import ContentCard from "app/components/page/ContentCard";

// MCP server "headers" arrive from the API as an object and live in the
// editor as a single `KEY: VALUE`-per-line textarea. Same parser used
// by the ProjectEdit page used to own; lifted here so MCP probe + save
// can build the right HTTP body shape.
function parseHeadersText(text) {
  const h = {};
  if (!text) return h;
  text.split("\n").forEach((line) => {
    const i = line.indexOf(":");
    if (i > 0) {
      const k = line.substring(0, i).trim();
      const v = line.substring(i + 1).trim();
      if (k) h[k] = v;
    }
  });
  return h;
}

const isStdioServer = (host) =>
  host && !host.startsWith("http://") && !host.startsWith("https://");

/**
 * Self-contained Tools editor for the project Info page.
 *
 * Used to live on the project Edit page (as `ProjectEditTools`, hooked
 * into the shared edit-form state machine). We moved it here so all
 * tool-related configuration lives next to the read-only summary the
 * user already saw on the Info tab — single place to inspect and tweak
 * built-in tools, MCP servers, agent loop settings, and agent-created
 * tools.
 *
 * The component renders the existing `ProjectEditTools` form (kept as
 * the rendering primitive) and owns its own state, fetches its own
 * tool catalog + MCP probes, and persists via PATCH /projects/{id}
 * with options merged on top of `project.options` (so we never wipe
 * unrelated keys like memory_bank, browser_, ftp_, etc.).
 */
export default function ProjectInfoTools({ project }) {
  const auth = useAuth();
  // Local copy of project, so save-then-refresh updates the chips
  // without forcing the parent to refetch.
  const [proj, setProj] = useState(project);
  // Form state — same shape as ProjectEditTools expects.
  const [state, setState] = useState({});
  // Tool catalog for the Autocomplete (`/tools/agent`).
  const [tools, setTools] = useState([]);
  // MCP servers in editor shape (host, args, env, headersText, tools,
  // availableTools, loading, error).
  const [mcpServers, setMcpServers] = useState([]);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState(null); // {sev, msg}

  useEffect(() => { setProj(project); }, [project]);

  // Mount + when project changes: hydrate form state from project,
  // load tool catalog, hydrate MCP servers and stagger their probes
  // (mirrors the original ProjectEdit mount behavior).
  useEffect(() => {
    if (!proj?.id) return;
    setState({
      llm: proj.llm,
      options: { ...(proj.options || {}) },
    });
    api.get("/tools/agent", auth.user.token).then(setTools).catch(() => {});

    if (proj.type === "agent" && proj.options?.mcp_servers) {
      const servers = proj.options.mcp_servers.map((s) => ({
        host: s.host,
        args: s.args || [],
        env: s.env || {},
        headersText: Object.entries(s.headers || {}).map(([k, v]) => `${k}: ${v}`).join("\n"),
        tools: s.tools || null,
        availableTools: s.tools
          ? s.tools.split(",").map((t) => ({ name: t.trim(), description: "", schema: "" }))
          : [],
        loading: false,
        error: null,
      }));
      setMcpServers(servers);
      // Stagger initial probes — same as ProjectEdit used to do, so a
      // project with many servers doesn't hammer the network on mount.
      servers.forEach((server, index) => {
        if (!server.host) return;
        setTimeout(() => {
          setMcpServers((prev) => {
            const next = [...prev];
            if (next[index]) next[index] = { ...next[index], loading: true, error: null };
            return next;
          });
          const body = { host: server.host };
          if (server.args && server.args.length > 0) body.args = server.args;
          if (server.env && Object.keys(server.env).length > 0) body.env = server.env;
          const h = parseHeadersText(server.headersText);
          if (Object.keys(h).length > 0) body.headers = h;
          api.post("/tools/mcp/probe", body, auth.user.token, { silent: true })
            .then((data) => {
              setMcpServers((prev) => {
                const next = [...prev];
                if (next[index]) {
                  next[index] = { ...next[index], availableTools: data.tools || [], loading: false, error: null };
                }
                return next;
              });
            })
            .catch((err) => {
              setMcpServers((prev) => {
                const next = [...prev];
                if (next[index]) {
                  next[index] = {
                    ...next[index], loading: false,
                    error: (err && err.detail) || (err && err.message) || "Probe failed",
                  };
                }
                return next;
              });
            });
        }, 150 * index);
      });
    } else {
      setMcpServers([]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proj?.id]);

  // --- MCP server handlers (lifted verbatim from the old ProjectEdit) ---
  const handleAddMcpServer = () => {
    setMcpServers([...mcpServers, { host: "", args: [], env: {}, tools: null, availableTools: [], loading: false, error: null }]);
  };
  const handleRemoveMcpServer = (index) => {
    setMcpServers(mcpServers.filter((_, i) => i !== index));
  };
  const handleMcpServerFieldChange = (index, field, value) => {
    const updated = [...mcpServers];
    updated[index] = { ...updated[index], [field]: value };
    setMcpServers(updated);
  };
  const mcpServersRef = useRef(mcpServers);
  mcpServersRef.current = mcpServers;
  const handleProbeMcpServer = (index) => {
    const server = mcpServersRef.current[index];
    setMcpServers((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], loading: true, error: null };
      return next;
    });
    const body = { host: server.host };
    if (server.args && server.args.length > 0) body.args = server.args;
    if (server.env && Object.keys(server.env).length > 0) body.env = server.env;
    const headers = parseHeadersText(server.headersText);
    if (Object.keys(headers).length > 0) body.headers = headers;
    api.post("/tools/mcp/probe", body, auth.user.token)
      .then((data) => {
        if (data.type === "gateway") {
          setMcpServers((prev) => {
            const next = [...prev];
            next[index] = { ...next[index], gateway: data, loading: false, error: null };
            return next;
          });
        } else {
          setMcpServers((prev) => {
            const next = [...prev];
            next[index] = { ...next[index], availableTools: data.tools || [], gateway: null, loading: false, error: null };
            return next;
          });
        }
      })
      .catch((err) => {
        setMcpServers((prev) => {
          const next = [...prev];
          next[index] = { ...next[index], loading: false, error: err.message };
          return next;
        });
      });
  };
  const handleAddGatewayServices = (index, selectedServices) => {
    const server = mcpServers[index];
    const baseUrl = server.host.replace(/\/+$/, "");
    const urlObj = new URL(baseUrl);
    const baseOrigin = urlObj.origin;
    const headersText = server.headersText || "";
    const newServers = selectedServices.map((service) => ({
      host: baseOrigin + service,
      args: [], env: {}, headersText,
      tools: null, availableTools: [], loading: false, error: null,
    }));
    setMcpServers((prev) => {
      const next = [...prev];
      next.splice(index, 1, ...newServers);
      return next;
    });
  };
  const handleMcpToolsChange = (index, selectedToolNames) => {
    const updated = [...mcpServers];
    updated[index] = { ...updated[index], tools: selectedToolNames.length > 0 ? selectedToolNames.join(",") : null };
    setMcpServers(updated);
  };

  // --- Save: PATCH options, MERGED on top of current proj.options. ---
  // The PATCH endpoint replaces the entire options blob with whatever
  // we send (Pydantic builds a full ProjectOptions, defaults fill in
  // missing fields), so any key we omit gets reset. To avoid wiping
  // unrelated tabs (Knowledge / Security / Integrations / etc.) we
  // start from `proj.options` and only overwrite the tool-related keys.
  const handleSave = () => {
    setSaving(true);
    const filteredMcpServers = mcpServers
      .filter((s) => s.host.trim() !== "")
      .map((s) => {
        const entry = { host: s.host, tools: s.tools || null };
        if (s.args && s.args.length > 0) entry.args = s.args;
        if (s.env && Object.keys(s.env).length > 0) entry.env = s.env;
        const h = parseHeadersText(s.headersText);
        if (Object.keys(h).length > 0) entry.headers = h;
        return entry;
      });
    const merged = {
      ...(proj.options || {}),
      tools: state.options?.tools ?? null,
      max_iterations: state.options?.max_iterations ?? 10,
      agent_mode: state.options?.agent_mode || "auto",
      auto_plan: !!state.options?.auto_plan,
      mcp_servers: filteredMcpServers.length > 0 ? filteredMcpServers : null,
    };
    api.patch(`/projects/${proj.id}`, { options: merged }, auth.user.token)
      .then(() => api.get(`/projects/${proj.id}`, auth.user.token))
      .then((fresh) => {
        setProj(fresh);
        setToast({ sev: "success", msg: "Tools saved." });
      })
      .catch((e) => setToast({ sev: "error", msg: (e && e.detail) || "Save failed." }))
      .finally(() => setSaving(false));
  };

  if (!state.options) {
    return <Box sx={{ textAlign: "center", py: 4 }}><CircularProgress size={24} /></Box>;
  }

  return (
    <ContentCard
      icon={<Build />}
      title="Tools"
      subtitle={`PROJECT/${String(project.id).padStart(4, "0")} · BUILTINS · MCP · AGENT LOOP`}
    >
      <ProjectEditTools
        state={state}
        setState={setState}
        handleChange={() => { /* unused by the form */ }}
        project={proj}
        mcpServers={mcpServers}
        setMcpServers={setMcpServers}
        tools={tools}
        handleAddMcpServer={handleAddMcpServer}
        handleRemoveMcpServer={handleRemoveMcpServer}
        handleMcpServerFieldChange={handleMcpServerFieldChange}
        handleProbeMcpServer={handleProbeMcpServer}
        handleMcpToolsChange={handleMcpToolsChange}
        handleAddGatewayServices={handleAddGatewayServices}
        isStdioServer={isStdioServer}
      />

      <Divider sx={{ my: 3 }} />
      <Box sx={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 2 }}>
        <Typography variant="caption" color="text.secondary">
          Saving updates only the tool-related options; other tabs are unaffected.
        </Typography>
        <Button
          variant="contained"
          color="primary"
          startIcon={saving ? <CircularProgress size={16} color="inherit" /> : <SaveIcon />}
          disabled={saving}
          onClick={handleSave}
        >
          {saving ? "Saving…" : "Save"}
        </Button>
      </Box>

      <Snackbar
        open={!!toast}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        {toast ? (
          <Alert severity={toast.sev} variant="filled" onClose={() => setToast(null)}>
            {toast.msg}
          </Alert>
        ) : null}
      </Snackbar>
    </ContentCard>
  );
}
