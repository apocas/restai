import { Box, Button, Card, Dialog, DialogActions, DialogContent, DialogContentText, DialogTitle, Grid } from "@mui/material";
import { Info, Storage, Shield, Extension, Description } from "@mui/icons-material";
import { useState, useEffect, useRef } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "app/utils/api";
import ProjectTabNav from "./ProjectTabNav";
import ProjectEditGeneral from "./ProjectEditGeneral";
import ProjectEditSystemPrompt from "./ProjectEditSystemPrompt";
import ProjectEditKnowledge from "./ProjectEditKnowledge";
import ProjectEditSecurity from "./ProjectEditSecurity";
import ProjectEditIntegrations from "./ProjectEditIntegrations";

// `system` tab is gated to rag/agent — block projects have no system prompt.
const ALL_TABS = [
  { key: "General",       nameKey: "projects.edit.tabs.general",      Icon: Info },
  { key: "System",        nameKey: "projects.edit.tabs.system",       Icon: Description, agentOrRag: true },
  { key: "Knowledge",     nameKey: "projects.edit.tabs.knowledge",    Icon: Storage, ragOnly: true },
  { key: "Security",      nameKey: "projects.edit.tabs.security",     Icon: Shield },
  { key: "Integrations",  nameKey: "projects.edit.tabs.integrations", Icon: Extension },
];

export default function ProjectEdit({ project, projects, info }) {
  const auth = useAuth();
  const { t } = useTranslation();
  const translatedTabs = ALL_TABS.map((tab) => ({
    ...tab,
    name: t(tab.nameKey),
  }));
  const [state, setState] = useState({});
  const [users, setUsers] = useState([]);
  const [teams, setTeams] = useState([]);
  const [promptVersions, setPromptVersions] = useState([]);
  const [showVersions, setShowVersions] = useState(false);
  const [active, setActive] = useState("General");
  const navigate = useNavigate();
  // Baseline snapshot for dirty-checking. JSON.stringify (no deep-equals dep)
  // is fine — small field set, ref changes in nested objects still show up.
  const baselineRef = useRef(null);
  const [pendingNav, setPendingNav] = useState(null);
  const dirty = baselineRef.current != null && JSON.stringify(state) !== baselineRef.current;
  const [fieldErrors, setFieldErrors] = useState({});

  const tabs = translatedTabs.filter((tab) => {
    if (tab.ragOnly && project.type !== "rag") return false;
    if (tab.agentOnly && !project.type === "agent") return false;
    if (tab.agentOrRag && !project.type === "agent" && project.type !== "rag") return false;
    return true;
  });

  const handleSubmit = (event) => {
    event.preventDefault();

    var opts = {
      name: project.name,
      llm: state.llm,
      embeddings: state.embeddings || "",
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

    // Tools/agent_mode/max_iterations/auto_plan/mcp_servers persist via the
    // ProjectInfoTools Save button. Don't touch them here — state.options was
    // hydrated from the project so save preserves existing values.

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
    opts.options.eval_llm = state.options.eval_llm || null;
    if (project.type === "agent") {
      opts.options.memory_bank_enabled = state.options.memory_bank_enabled || false;
      opts.options.memory_bank_max_tokens = parseInt(state.options.memory_bank_max_tokens) || 2000;
      opts.options.memory_search_enabled = state.options.memory_search_enabled || false;
      opts.options.browser_allowed_domains = state.options.browser_allowed_domains || null;
      opts.options.browser_allow_eval = !!state.options.browser_allow_eval;
      opts.options.agent_loop = state.options.agent_loop || null;
    }

    if (project.type === "rag") {
      opts.options.llm_rerank = state.options.llm_rerank;
      opts.options.rerank_llm = state.options.rerank_llm || null;
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
        // Reset baseline so the navigate doesn't trigger the unsaved guard.
        baselineRef.current = JSON.stringify(state);
        setFieldErrors({});
        navigate("/project/" + project.id);
      })
      .catch((err) => {
        // Pydantic 422 → fieldErrors map from api.js; tabs render inline helpers.
        const fe = err && err.fieldErrors ? err.fieldErrors : {};
        setFieldErrors(fe);
      });
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();

    if (["logging", "redact_inference_logs", "llm_rerank", "enable_knowledge_graph", "memory_bank_enabled", "memory_search_enabled", "browser_allow_eval"].includes(event.target.name)) {
      setState({ ...state, options: { ...state.options, [event.target.name]: event.target.checked } });
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

  useEffect(() => {
    const initialState = {
      ...project,
      options: {
        logging: false,
        llm_rerank: false,
        score: 0.0,
        k: 4,
        tools: null,
        memory_bank_enabled: false,
        memory_bank_max_tokens: 2000,
        memory_search_enabled: false,
        ...project.options,
      },
    };

    setState(initialState);
    // Record baseline synchronously with the state we're installing —
    // React's committed state will be value-equal to initialState.
    baselineRef.current = JSON.stringify(initialState);

    api.get("/users", auth.user.token).then((d) => setUsers(d.users)).catch(() => {});
    api.get("/teams", auth.user.token).then((d) => setTeams(d.teams || [])).catch(() => {});

    if (project.id && project.type !== "block") {
      api.get("/projects/" + project.id + "/prompts", auth.user.token, { silent: true })
        .then((versions) => setPromptVersions(versions || []))
        .catch(() => {});
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

  // beforeunload warning. Modern browsers ignore the custom message and
  // show their own — setting `returnValue` is what triggers the dialog.
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
    // Reset baseline so the unmount doesn't re-fire beforeunload.
    baselineRef.current = JSON.stringify(state);
    if (path) navigate(path);
  };

  return (
    <form onSubmit={handleSubmit}>
      <Card
        elevation={0}
        sx={{
          p: 1.5, mb: 2,
          borderRadius: 3,
          border: "1px solid",
          borderColor: "divider",
          backgroundColor: "background.paper",
        }}
      >
        <Box sx={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 1 }}>
          <Button
            variant="outlined"
            onClick={() => requestNavigate("/project/" + project.id)}
          >{t("common.cancel")}</Button>
          <Button type="submit" variant="contained" color="primary">{t("common.save")}{dirty ? "*" : ""}</Button>
        </Box>
      </Card>

      <Grid container spacing={3}>
        <Grid item md={2} xs={12}>
          <ProjectTabNav tabs={tabs} active={active} setActive={setActive} />
        </Grid>

        <Grid item md={10} xs={12}>
          <Box>
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
            {active === "System" && (
              <ProjectEditSystemPrompt
                state={state} setState={setState}
                project={project} info={info}
                promptVersions={promptVersions}
                showVersions={showVersions}
                setShowVersions={setShowVersions}
              />
            )}
            {active === "Knowledge" && (
              <ProjectEditKnowledge
                state={state} setState={setState} handleChange={handleChange}
                project={project} auth={auth} info={info}
                fieldErrors={fieldErrors}
                clearFieldError={(k) => setFieldErrors((prev) => {
                  if (!(k in prev)) return prev;
                  const next = { ...prev }; delete next[k]; return next;
                })}
              />
            )}
            {active === "Security" && (
              <ProjectEditSecurity
                state={state} setState={setState} handleChange={handleChange}
                projects={projects} project={project}
                fieldErrors={fieldErrors}
                clearFieldError={(k) => setFieldErrors((prev) => {
                  if (!(k in prev)) return prev;
                  const next = { ...prev }; delete next[k]; return next;
                })}
              />
            )}
            {active === "Integrations" && (
              <ProjectEditIntegrations
                state={state} setState={setState} handleChange={handleChange} project={project}
              />
            )}
          </Box>
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
