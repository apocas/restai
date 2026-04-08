import { Box, Button, Card, Grid, styled } from "@mui/material";
import { Info, Storage, Shield, Extension, Build } from "@mui/icons-material";
import { H4 } from "app/components/Typography";
import { useState, useEffect, useRef } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import api from "app/utils/api";
import ProjectTabNav from "./ProjectTabNav";
import ProjectEditGeneral from "./ProjectEditGeneral";
import ProjectEditKnowledge from "./ProjectEditKnowledge";
import ProjectEditSecurity from "./ProjectEditSecurity";
import ProjectEditIntegrations from "./ProjectEditIntegrations";
import ProjectEditTools from "./ProjectEditTools";

function parseHeadersText(text) {
  const h = {};
  if (!text) return h;
  text.split("\n").forEach(line => {
    const i = line.indexOf(":");
    if (i > 0) { const k = line.substring(0, i).trim(); const v = line.substring(i + 1).trim(); if (k) h[k] = v; }
  });
  return h;
}

const ALL_TABS = [
  { name: "General", Icon: Info },
  { name: "Knowledge", Icon: Storage, ragOnly: true },
  { name: "Tools", Icon: Build, agentOnly: true },
  { name: "Security", Icon: Shield },
  { name: "Integrations", Icon: Extension },
];

export default function ProjectEdit({ project, projects, info }) {
  const auth = useAuth();
  const [state, setState] = useState({});
  const [tools, setTools] = useState([]);
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [mcpServers, setMcpServers] = useState([]);
  const [promptVersions, setPromptVersions] = useState([]);
  const [showVersions, setShowVersions] = useState(false);
  const [active, setActive] = useState("General");
  const navigate = useNavigate();

  const tabs = ALL_TABS.filter((t) => {
    if (t.ragOnly && project.type !== "rag") return false;
    if (t.agentOnly && project.type !== "agent") return false;
    return true;
  });

  // --- MCP Server Handlers ---
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
    setMcpServers(prev => {
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
          setMcpServers(prev => {
            const next = [...prev];
            next[index] = { ...next[index], gateway: data, loading: false, error: null };
            return next;
          });
        } else {
          setMcpServers(prev => {
            const next = [...prev];
            next[index] = { ...next[index], availableTools: data.tools || [], gateway: null, loading: false, error: null };
            return next;
          });
        }
      })
      .catch((err) => {
        setMcpServers(prev => {
          const next = [...prev];
          next[index] = { ...next[index], loading: false, error: err.message };
          return next;
        });
      });
  };

  const handleAddGatewayServices = (index, selectedServices) => {
    const server = mcpServers[index];
    const baseUrl = server.host.replace(/\/+$/, "");
    // Extract base URL without the gateway path
    const urlObj = new URL(baseUrl);
    const baseOrigin = urlObj.origin;

    const headersText = server.headersText || "";
    const newServers = selectedServices.map(service => ({
      host: baseOrigin + service,
      args: [],
      env: {},
      headersText: headersText,
      tools: null,
      availableTools: [],
      loading: false,
      error: null,
    }));

    setMcpServers(prev => {
      const next = [...prev];
      next.splice(index, 1, ...newServers); // Replace gateway entry with individual servers
      return next;
    });
  };

  const handleMcpToolsChange = (index, selectedToolNames) => {
    const updated = [...mcpServers];
    updated[index] = { ...updated[index], tools: selectedToolNames.length > 0 ? selectedToolNames.join(",") : null };
    setMcpServers(updated);
  };

  const isStdioServer = (host) => {
    return host && !host.startsWith("http://") && !host.startsWith("https://");
  };

  // --- Form Submission ---
  const handleSubmit = (event) => {
    event.preventDefault();

    var opts = {
      name: project.name,
      llm: state.llm,
      human_description: state.human_description,
      human_name: state.human_name,
      guard: state.guard || "",
      censorship: state.censorship || "",
      public: state.public,
      default_prompt: state.default_prompt || "",
      options: state.options || {},
    };

    if (state.options.logging !== undefined) {
      opts.options.logging = state.options.logging;
    }

    if (state.team && state.team.id) {
      opts.team_id = state.team.id;
    }

    if (state.selectedUsers && state.selectedUsers.length > 0) {
      opts.users = state.selectedUsers.map((user) => user.username);
    }

    if (project.type === "rag" || project.type === "inference" || project.type === "agent") {
      opts.system = state.system;
    }

    if (project.type === "agent") {
      opts.options.tools = state.options.tools;
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
      opts.options.mcp_servers = filteredMcpServers.length > 0 ? filteredMcpServers : null;
    }

    if (state.options.telegram_token !== undefined) opts.options.telegram_token = state.options.telegram_token;
    if (state.options.slack_bot_token !== undefined) opts.options.slack_bot_token = state.options.slack_bot_token;
    if (state.options.slack_app_token !== undefined) opts.options.slack_app_token = state.options.slack_app_token;

    opts.options.rate_limit = state.options.rate_limit ? parseInt(state.options.rate_limit) : null;
    opts.options.guard_output = state.options.guard_output || null;
    opts.options.guard_mode = state.options.guard_mode || "block";
    opts.options.fallback_llm = state.options.fallback_llm || null;
    opts.options.cache = state.options.cache;
    opts.options.cache_threshold = parseFloat(state.options.cache_threshold) || 0.85;

    if (project.type === "rag") {
      opts.options.colbert_rerank = state.options.colbert_rerank;
      opts.options.llm_rerank = state.options.llm_rerank;
      opts.options.score = parseFloat(state.options.score) || 0.0;
      opts.options.k = parseInt(state.options.k) || 4;
      opts.options.connection = state.options.connection || null;
      opts.options.tables = state.options.tables || null;
      opts.options.sync_enabled = state.options.sync_enabled || false;
      opts.options.sync_sources = state.options.sync_sources || null;
      opts.options.enable_knowledge_graph = state.options.enable_knowledge_graph || false;

      if (opts.censorship && opts.censorship.trim() === "") {
        delete opts.options.censorship;
      }
    }

    api.patch("/projects/" + project.id, opts, auth.user.token)
      .then(() => navigate("/project/" + project.id))
      .catch(() => {});
  };

  // --- Change Handlers ---
  const handleChange = (event) => {
    if (event && event.persist) event.persist();

    if (["logging", "cache", "llm_rerank", "colbert_rerank", "enable_knowledge_graph"].includes(event.target.name)) {
      setState({ ...state, options: { ...state.options, [event.target.name]: event.target.checked } });
    } else if (event.target.name === "cache_threshold") {
      setState({ ...state, options: { ...state.options, cache_threshold: event.target.value / 100 } });
    } else if (event.target.name === "k") {
      setState({ ...state, options: { ...state.options, k: parseInt(event.target.value) } });
    } else if (event.target.name === "score") {
      setState({ ...state, options: { ...state.options, score: event.target.value } });
    } else if (event.target.name === "telegram_token") {
      setState({ ...state, options: { ...state.options, telegram_token: event.target.value } });
    } else if (event.target.name === "connection" || event.target.name === "tables") {
      setState({ ...state, options: { ...state.options, [event.target.name]: event.target.value } });
    } else if (event.target.name === "rate_limit") {
      setState({ ...state, options: { ...state.options, rate_limit: event.target.value ? parseInt(event.target.value) : null } });
    } else {
      setState({ ...state, [event.target.name]: event.target.type === "checkbox" ? event.target.checked : event.target.value });
    }
  };

  const handleTeamChange = (event) => {
    const teamId = event.target.value;
    setState((prev) => ({ ...prev, team_id: teamId }));

    if (teamId) {
      api.get("/teams/" + teamId, auth.user.token)
        .then((teamData) => setState((prev) => ({ ...prev, team: teamData })))
        .catch(() => {});
    } else {
      setState((prev) => ({ ...prev, team: null }));
    }
  };

  // --- Data Fetching ---
  useEffect(() => {
    const initialState = {
      ...project,
      options: {
        logging: false,
        colbert_rerank: false,
        llm_rerank: false,
        cache: false,
        cache_threshold: 0.85,
        score: 0.0,
        k: 4,
        tools: null,
        ...project.options,
      },
    };

    setState(initialState);

    api.get("/tools/agent", auth.user.token).then(setTools).catch(() => {});
    api.get("/users", auth.user.token).then((d) => setUsers(d.users)).catch(() => {});
    api.get("/teams", auth.user.token).then((d) => setTeams(d.teams || [])).catch(() => {});

    if (project.id && project.type !== "block") {
      api.get("/projects/" + project.id + "/prompts", auth.user.token, { silent: true })
        .then((versions) => setPromptVersions(versions || []))
        .catch(() => {});
    }

    if (project.type === "agent" && project.options?.mcp_servers) {
      const servers = project.options.mcp_servers.map((s) => ({
        host: s.host,
        args: s.args || [],
        env: s.env || {},
        headersText: Object.entries(s.headers || {}).map(([k, v]) => `${k}: ${v}`).join("\n"),
        tools: s.tools || null,
        availableTools: s.tools ? s.tools.split(",").map((t) => ({ name: t.trim(), description: "", schema: "" })) : [],
        loading: false,
        error: null,
      }));
      setMcpServers(servers);

      servers.forEach((server, index) => {
        if (server.host) {
          const body = { host: server.host };
          if (server.args && server.args.length > 0) body.args = server.args;
          if (server.env && Object.keys(server.env).length > 0) body.env = server.env;
          const h = parseHeadersText(server.headersText);
          if (Object.keys(h).length > 0) body.headers = h;
          api.post("/tools/mcp/probe", body, auth.user.token, { silent: true })
            .then((data) => {
              setMcpServers((prev) => {
                const next = [...prev];
                next[index] = { ...next[index], availableTools: data.tools || [] };
                return next;
              });
            })
            .catch(() => {});
        }
      });
    }

    if (project?.team?.id) {
      api.get("/teams/" + project.team.id, auth.user.token, { silent: true })
        .then((teamData) => setState((prev) => ({ ...prev, team: teamData })))
        .catch(() => {});
    }
  }, [project, auth.user.token]);

  useEffect(() => {
    if (project && project.users) {
      const projectUsers = users.filter((user) => project.users.includes(user.username));
      setState((prev) => ({ ...prev, selectedUsers: projectUsers }));
    }
  }, [users, project]);

  return (
    <form onSubmit={handleSubmit}>
      <Card elevation={3} sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <H4>Edit project - {project.name}</H4>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button variant="outlined" onClick={() => navigate("/project/" + project.id)}>Cancel</Button>
            <Button type="submit" variant="contained" color="primary">Save</Button>
          </Box>
        </Box>
      </Card>

      <Grid container spacing={3}>
        <Grid item md={2} xs={12}>
          <ProjectTabNav tabs={tabs} active={active} setActive={setActive} />
        </Grid>

        <Grid item md={10} xs={12}>
          <Card elevation={1} sx={{ p: 3 }}>
            {active === "General" && (
              <ProjectEditGeneral
                state={state} setState={setState} handleChange={handleChange}
                project={project} info={info} users={users} teams={teams}
                promptVersions={promptVersions} showVersions={showVersions}
                setShowVersions={setShowVersions} handleTeamChange={handleTeamChange}
              />
            )}
            {active === "Knowledge" && (
              <ProjectEditKnowledge
                state={state} setState={setState} handleChange={handleChange}
                project={project} auth={auth}
              />
            )}
            {active === "Tools" && (
              <ProjectEditTools
                state={state} setState={setState} handleChange={handleChange}
                project={project} mcpServers={mcpServers} setMcpServers={setMcpServers}
                tools={tools} handleAddMcpServer={handleAddMcpServer}
                handleRemoveMcpServer={handleRemoveMcpServer}
                handleMcpServerFieldChange={handleMcpServerFieldChange}
                handleProbeMcpServer={handleProbeMcpServer}
                handleMcpToolsChange={handleMcpToolsChange}
                handleAddGatewayServices={handleAddGatewayServices}
                isStdioServer={isStdioServer}
              />
            )}
            {active === "Security" && (
              <ProjectEditSecurity
                state={state} setState={setState} handleChange={handleChange}
                projects={projects}
              />
            )}
            {active === "Integrations" && (
              <ProjectEditIntegrations
                state={state} setState={setState} handleChange={handleChange}
              />
            )}
          </Card>
        </Grid>
      </Grid>
    </form>
  );
}
