import { Box, Button, Card, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Grid, styled } from "@mui/material";
import { Info, Storage, Shield, Extension, Build, VpnKey } from "@mui/icons-material";
import { H4 } from "app/components/Typography";
import { useState, useEffect, useRef } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import ProjectTabNav from "./ProjectTabNav";
import ProjectEditGeneral from "./ProjectEditGeneral";
import ProjectEditKnowledge from "./ProjectEditKnowledge";
import ProjectEditSecurity from "./ProjectEditSecurity";
import ProjectEditIntegrations from "./ProjectEditIntegrations";
import ProjectEditTools from "./ProjectEditTools";
import ProjectEditSecrets from "./ProjectEditSecrets";

function parseHeadersText(text) {
  const h = {};
  if (!text) return h;
  text.split("\n").forEach(line => {
    const i = line.indexOf(":");
    if (i > 0) { const k = line.substring(0, i).trim(); const v = line.substring(i + 1).trim(); if (k) h[k] = v; }
  });
  return h;
}

// Tab definitions. `key` stays stable (used internally for conditional
// rendering); `name` is resolved via i18n at render time.
const ALL_TABS = [
  { key: "General",       nameKey: "projects.edit.tabs.general",      Icon: Info },
  { key: "Knowledge",     nameKey: "projects.edit.tabs.knowledge",    Icon: Storage, ragOnly: true },
  { key: "Tools",         nameKey: "projects.edit.tabs.tools",        Icon: Build,   agentOnly: true },
  { key: "Secrets",       nameKey: "projects.edit.tabs.secrets",      Icon: VpnKey,  agentOnly: true },
  { key: "Security",      nameKey: "projects.edit.tabs.security",     Icon: Shield },
  { key: "Integrations",  nameKey: "projects.edit.tabs.integrations", Icon: Extension },
];

export default function ProjectEdit({ project, projects, info }) {
  const auth = useAuth();
  const { t } = useTranslation();
  // Tabs translated at render time so language switch re-renders them.
  const translatedTabs = ALL_TABS.map((tab) => ({
    ...tab,
    name: t(tab.nameKey),
  }));
  const [state, setState] = useState({});
  const [tools, setTools] = useState([]);
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [mcpServers, setMcpServers] = useState([]);
  const [promptVersions, setPromptVersions] = useState([]);
  const [showVersions, setShowVersions] = useState(false);
  const [active, setActive] = useState("General");
  const navigate = useNavigate();
  // Snapshot of the form state immediately after `setState(initialState)`
  // runs in the load effect. Compared against `state` on every render to
  // derive `dirty`. We intentionally compare via JSON.stringify rather
  // than a deep-equals lib — the field set is small enough and avoids a
  // dep, and any spurious reference change in `state.team` etc. would
  // be reflected in the JSON anyway.
  const baselineRef = useRef(null);
  const [pendingNav, setPendingNav] = useState(null);
  const dirty = baselineRef.current != null && JSON.stringify(state) !== baselineRef.current;
  // fieldErrors: map of field name → message, populated from a 422
  // response on save. Cleared when the user types in that field or
  // when a save succeeds. Handed down to tab components via prop.
  const [fieldErrors, setFieldErrors] = useState({});

  // Filter the *translated* tabs so the mobile drawer shows the right
  // language in its per-tab label. Using a different variable name
  // than `t` to avoid shadowing the i18n helper.
  const tabs = translatedTabs.filter((tab) => {
    if (tab.ragOnly && project.type !== "rag") return false;
    if (tab.agentOnly && project.type !== "agent") return false;
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

    if (state.options.redact_inference_logs !== undefined) {
      opts.options.redact_inference_logs = state.options.redact_inference_logs;
    }

    if (state.team && state.team.id) {
      opts.team_id = state.team.id;
    }

    if (state.selectedUsers !== undefined) {
      opts.users = (state.selectedUsers || []).map((user) => user.username);
    }

    if (project.type === "rag" || project.type === "agent") {
      opts.system = state.system;
    }

    if (project.type === "agent") {
      opts.options.tools = state.options.tools;
      opts.options.agent_mode = state.options.agent_mode || "auto";
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
    if (state.options.telegram_default_chat_id !== undefined) opts.options.telegram_default_chat_id = state.options.telegram_default_chat_id || null;
    if (state.options.telegram_allowed_chat_ids !== undefined) opts.options.telegram_allowed_chat_ids = state.options.telegram_allowed_chat_ids || null;
    if (state.options.slack_bot_token !== undefined) opts.options.slack_bot_token = state.options.slack_bot_token;
    if (state.options.slack_app_token !== undefined) opts.options.slack_app_token = state.options.slack_app_token;

    if (state.options.whatsapp_phone_number_id !== undefined) opts.options.whatsapp_phone_number_id = state.options.whatsapp_phone_number_id || null;
    if (state.options.whatsapp_access_token !== undefined) opts.options.whatsapp_access_token = state.options.whatsapp_access_token || null;
    if (state.options.whatsapp_app_secret !== undefined) opts.options.whatsapp_app_secret = state.options.whatsapp_app_secret || null;
    if (state.options.whatsapp_verify_token !== undefined) opts.options.whatsapp_verify_token = state.options.whatsapp_verify_token || null;
    if (state.options.whatsapp_default_to !== undefined) opts.options.whatsapp_default_to = state.options.whatsapp_default_to || null;
    if (state.options.whatsapp_allowed_phone_numbers !== undefined) opts.options.whatsapp_allowed_phone_numbers = state.options.whatsapp_allowed_phone_numbers || null;

    if (state.options.smtp_host !== undefined) opts.options.smtp_host = state.options.smtp_host || null;
    if (state.options.smtp_port !== undefined) opts.options.smtp_port = state.options.smtp_port ? parseInt(state.options.smtp_port) : null;
    if (state.options.smtp_user !== undefined) opts.options.smtp_user = state.options.smtp_user || null;
    if (state.options.smtp_password !== undefined) opts.options.smtp_password = state.options.smtp_password || null;
    if (state.options.smtp_from !== undefined) opts.options.smtp_from = state.options.smtp_from || null;
    if (state.options.email_default_to !== undefined) opts.options.email_default_to = state.options.email_default_to || null;
    if (state.options.twilio_account_sid !== undefined) opts.options.twilio_account_sid = state.options.twilio_account_sid || null;
    if (state.options.twilio_auth_token !== undefined) opts.options.twilio_auth_token = state.options.twilio_auth_token || null;
    if (state.options.twilio_from_number !== undefined) opts.options.twilio_from_number = state.options.twilio_from_number || null;
    if (state.options.sms_default_to !== undefined) opts.options.sms_default_to = state.options.sms_default_to || null;

    if (state.options.webhook_url !== undefined) opts.options.webhook_url = state.options.webhook_url || null;
    if (state.options.webhook_secret !== undefined) opts.options.webhook_secret = state.options.webhook_secret || null;
    if (state.options.webhook_events !== undefined) opts.options.webhook_events = state.options.webhook_events || null;

    opts.options.rate_limit = state.options.rate_limit ? parseInt(state.options.rate_limit) : null;
    opts.options.guard_output = state.options.guard_output || null;
    opts.options.guard_mode = state.options.guard_mode || "block";
    opts.options.cache = state.options.cache;
    opts.options.cache_threshold = parseFloat(state.options.cache_threshold) || 0.85;
    if (project.type === "agent") {
      opts.options.memory_bank_enabled = state.options.memory_bank_enabled || false;
      opts.options.memory_bank_max_tokens = parseInt(state.options.memory_bank_max_tokens) || 2000;
      opts.options.browser_allowed_domains = state.options.browser_allowed_domains || null;
      opts.options.browser_allow_eval = !!state.options.browser_allow_eval;
    }

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
      .then(() => {
        // Save succeeded — clear the dirty baseline so the navigate
        // away doesn't trigger the unsaved-changes guard.
        baselineRef.current = JSON.stringify(state);
        setFieldErrors({});
        navigate("/project/" + project.id);
      })
      .catch((err) => {
        // Pydantic-422 errors arrive with a `fieldErrors` map from
        // api.js — stash them so the tab components can show inline
        // helper text. Switch to General tab if that's where the
        // offending fields live (the ones most likely to 422 —
        // numeric bounds on k / score / rate_limit).
        const fe = err && err.fieldErrors ? err.fieldErrors : {};
        setFieldErrors(fe);
      });
  };

  // --- Change Handlers ---
  const handleChange = (event) => {
    if (event && event.persist) event.persist();

    if (["logging", "redact_inference_logs", "cache", "llm_rerank", "colbert_rerank", "enable_knowledge_graph", "memory_bank_enabled", "browser_allow_eval"].includes(event.target.name)) {
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
    } else if (event.target.name === "memory_bank_max_tokens") {
      const v = parseInt(event.target.value);
      setState({ ...state, options: { ...state.options, memory_bank_max_tokens: Number.isFinite(v) ? v : 2000 } });
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
        memory_bank_enabled: false,
        memory_bank_max_tokens: 2000,
        ...project.options,
      },
    };

    setState(initialState);
    // Record the baseline synchronously with the same state we're about
    // to install. The `state` React commits will be equal-by-value to
    // `initialState`, so JSON.stringify of either yields the same string.
    baselineRef.current = JSON.stringify(initialState);

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

      // Stagger initial probes by 150ms each. A project with 10 MCP
      // servers used to fire 10 parallel POSTs on mount — fine for a
      // lab setup, noisy for a production deployment where each probe
      // reaches out to a different remote. Also flips `loading` + fills
      // `error` on failure so the new Retry button has state to show.
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
                  next[index] = {
                    ...next[index],
                    availableTools: data.tools || [],
                    loading: false,
                    error: null,
                  };
                }
                return next;
              });
            })
            .catch((err) => {
              setMcpServers((prev) => {
                const next = [...prev];
                if (next[index]) {
                  next[index] = {
                    ...next[index],
                    loading: false,
                    error: (err && err.detail) || (err && err.message) || "Probe failed",
                  };
                }
                return next;
              });
            });
        }, index * 150);
      });
    }

    if (project?.team?.id) {
      api.get("/teams/" + project.team.id, auth.user.token, { silent: true })
        .then((teamData) => setState((prev) => ({ ...prev, team: teamData })))
        .catch(() => {});
    }
  }, [project, auth.user.token]);

  useEffect(() => {
    if (project && Array.isArray(project.users)) {
      const projectUsernames = project.users.map((u) => typeof u === "string" ? u : u?.username);
      const projectUsers = users.filter((user) => projectUsernames.includes(user.username));
      setState((prev) => ({ ...prev, selectedUsers: projectUsers }));
    }
  }, [users, project]);

  // Browser-level guard: warns on tab close, refresh, or address-bar
  // navigation while there are unsaved edits. The custom message is
  // ignored by every modern browser (they show a generic prompt) but
  // setting `returnValue` is what actually triggers the dialog.
  useEffect(() => {
    if (!dirty) return undefined;
    const handler = (e) => {
      e.preventDefault();
      e.returnValue = "";
      return "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // Intercepts the Cancel button (and any other in-app navigation we
  // route through here) so the user gets a confirm dialog instead of
  // silently losing edits. When dirty=false this just navigates.
  const requestNavigate = (path) => {
    if (dirty) {
      setPendingNav(path);
    } else {
      navigate(path);
    }
  };
  const confirmDiscard = () => {
    const path = pendingNav;
    setPendingNav(null);
    // Clear the baseline so the unmount doesn't fire beforeunload again.
    baselineRef.current = JSON.stringify(state);
    if (path) navigate(path);
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card elevation={3} sx={{ p: 2, mb: 2 }}>
        <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <H4>{t("projects.edit.title", { name: project.name })}</H4>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button variant="outlined" onClick={() => requestNavigate("/project/" + project.id)}>{t("common.cancel")}</Button>
            <Button type="submit" variant="contained" color="primary">{t("common.save")}{dirty ? "*" : ""}</Button>
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
                fieldErrors={fieldErrors}
                clearFieldError={(k) => setFieldErrors((prev) => {
                  if (!(k in prev)) return prev;
                  const next = { ...prev };
                  delete next[k];
                  return next;
                })}
              />
            )}
            {active === "Knowledge" && (
              <ProjectEditKnowledge
                state={state} setState={setState} handleChange={handleChange}
                project={project} auth={auth}
                fieldErrors={fieldErrors}
                clearFieldError={(k) => setFieldErrors((prev) => {
                  if (!(k in prev)) return prev;
                  const next = { ...prev }; delete next[k]; return next;
                })}
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
                fieldErrors={fieldErrors}
                clearFieldError={(k) => setFieldErrors((prev) => {
                  if (!(k in prev)) return prev;
                  const next = { ...prev }; delete next[k]; return next;
                })}
              />
            )}
            {active === "Secrets" && (
              <ProjectEditSecrets project={project} />
            )}
            {active === "Integrations" && (
              <ProjectEditIntegrations
                state={state} setState={setState} handleChange={handleChange} project={project}
              />
            )}
          </Card>
        </Grid>
      </Grid>

      <Dialog open={pendingNav != null} onClose={() => setPendingNav(null)}>
        <DialogTitle>{t("projects.unsavedChanges.title")}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t("projects.unsavedChanges.message")}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPendingNav(null)}>{t("common.keepEditing")}</Button>
          <Button onClick={confirmDiscard} color="error" variant="contained">{t("common.discard")}</Button>
        </DialogActions>
      </Dialog>
    </form>
  );
}
