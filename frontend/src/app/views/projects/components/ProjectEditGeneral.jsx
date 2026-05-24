import {
  Alert, Autocomplete, Box, FormControlLabel, MenuItem,
  Switch, TextField, Tooltip,
} from "@mui/material";
import { HelpOutline, Settings } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import ContentCard from "app/components/page/ContentCard";
import { FONT_MONO } from "app/components/page/pageStyles";
import { makeErrorFor } from "./projectOptionValidators";
import { SectionHeader, sectionShellSx } from "./integrationsKit";

const ID_ACCENT     = "#0ea5e9";
const ACCESS_ACCENT = "#10b981";
const MODEL_ACCENT  = "#8b5cf6";
const MEM_ACCENT    = "#ec4899";
const BROWSER_ACCENT = "#14b8a6";
const LOOP_ACCENT   = "#6366f1";

const HelpTip = ({ text }) => (
  <Tooltip title={text} placement="top" arrow>
    <HelpOutline sx={{ fontSize: 16, color: "text.disabled", ml: 0.5, cursor: "help", verticalAlign: "middle" }} />
  </Tooltip>
);

function Section({ accent, children }) {
  return (
    <Box sx={{ ...sectionShellSx(accent), p: 2.5, display: "flex", flexDirection: "column", gap: 2 }}>
      {children}
    </Box>
  );
}

function FieldGrid({ children }) {
  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr" }, gap: 2 }}>
      {children}
    </Box>
  );
}

export default function ProjectEditGeneral({
  state, setState, handleChange, project, info, users, teams,
  handleTeamChange, fieldErrors = {}, clearFieldError = () => {},
}) {
  const { t } = useTranslation();
  const errorFor = makeErrorFor(fieldErrors, state);
  const opts = state.options || {};

  const teamId = state.team ? state.team.id : (project.team ? project.team.id : "");
  const llmsForTeam = info.llms.filter((l) => {
    if (!state.team) return true;
    const teamLlms = (state.team.llms || []).map((x) => (typeof x === "string" ? x : x.name));
    return teamLlms.includes(l.name);
  });
  const embeddingsForTeam = (info.embeddings || []).filter((e) => {
    if (!state.team) return true;
    const teamEmbs = (state.team.embeddings || []).map((x) => (typeof x === "string" ? x : x.name));
    return teamEmbs.includes(e.name);
  });

  const accessLive = !!(state.public || (state.selectedUsers && state.selectedUsers.length > 0));

  return (
    <ContentCard
      icon={<Settings />}
      title="General"
      subtitle={`PROJECT/${String(project.id).padStart(4, "0")} · IDENTITY · ACCESS · MODEL · MEMORY`}
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>

        {/* ── IDENTITY ──────────────────────────────────────── */}
        <Section accent={ID_ACCENT}>
          <SectionHeader
            title="Identity"
            accent={ID_ACCENT}
            subtitle="Public-facing name + one-line summary."
          />
          <FieldGrid>
            <TextField
              fullWidth size="small"
              InputLabelProps={{ shrink: true }}
              name="human_name"
              label={t("projects.edit.general.displayName")}
              value={state.human_name ?? ""}
              onChange={handleChange}
            />
            <TextField
              fullWidth size="small"
              InputLabelProps={{ shrink: true }}
              name="human_description"
              label={t("projects.edit.general.description")}
              value={state.human_description ?? ""}
              onChange={handleChange}
            />
          </FieldGrid>
        </Section>

        {/* ── ACCESS ────────────────────────────────────────── */}
        <Section accent={ACCESS_ACCENT}>
          <SectionHeader
            title="Access"
            accent={ACCESS_ACCENT}
            subtitle="Visibility, audit logging, team & individual users."
          />
          <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
            {state.public !== undefined && (
              <FormControlLabel
                label={<span>Shared<HelpTip text="When enabled, all users on the platform can access this project" /></span>}
                control={<Switch checked={state.public} name="public" onChange={handleChange} />}
              />
            )}
            <FormControlLabel
              label={<span>Logging<HelpTip text="Records all requests and responses for analytics and debugging" /></span>}
              control={<Switch checked={opts.logging ?? false} name="logging" onChange={handleChange} />}
            />
            <FormControlLabel
              label={<span>Redact secrets in logs<HelpTip text="Strip API keys, tokens and credentials from question/answer/system prompt before persisting" /></span>}
              control={
                <Switch
                  checked={opts.redact_inference_logs ?? false}
                  name="redact_inference_logs"
                  onChange={handleChange}
                  disabled={!(opts.logging ?? false)}
                />
              }
            />
          </Box>
          <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "1fr 2fr" }, gap: 2 }}>
            <TextField
              select fullWidth size="small"
              name="team_id"
              label={t("common.team")}
              value={teamId}
              onChange={handleTeamChange}
            >
              {teams.map((team) => (
                <MenuItem value={team.id} key={team.id}>{team.name}</MenuItem>
              ))}
            </TextField>
            <Autocomplete
              multiple size="small"
              id="users-select"
              options={users}
              getOptionLabel={(option) => option.username}
              value={state.selectedUsers || []}
              isOptionEqualToValue={(option, value) => option.username === value.username}
              onChange={(_, newValue) => setState({ ...state, selectedUsers: newValue })}
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t("nav.users")}
                  placeholder="Select users"
                  helperText="Direct assignments — bypasses team membership"
                />
              )}
            />
          </Box>
        </Section>

        {/* ── MODEL ─────────────────────────────────────────── */}
        {state.type !== "block" && (
          <Section accent={MODEL_ACCENT}>
            <SectionHeader
              title="Model"
              accent={MODEL_ACCENT}
              subtitle="LLM that powers chat. Embedding powers RAG retrieval and conversation memory search."
            />
            <FieldGrid>
              {state.llm !== undefined && (
                <TextField
                  fullWidth select size="small"
                  name="llm"
                  label={t("projects.edit.general.llm")}
                  value={state.llm ?? ""}
                  onChange={handleChange}
                >
                  {llmsForTeam.map((item) => (
                    <MenuItem value={item.name} key={item.name}>{item.name}</MenuItem>
                  ))}
                </TextField>
              )}
              <TextField
                fullWidth select size="small"
                name="embeddings"
                label="Embeddings"
                value={state.embeddings ?? ""}
                onChange={(e) => setState({ ...state, embeddings: e.target.value })}
                helperText="Used for RAG (RAG projects) and conversation memory search (agent + Memory Search on)."
                InputLabelProps={{ shrink: true }}
                SelectProps={{ displayEmpty: true }}
              >
                <MenuItem value=""><em>None</em></MenuItem>
                {embeddingsForTeam.map((item) => (
                  <MenuItem value={item.name} key={item.name}>{item.name}</MenuItem>
                ))}
              </TextField>
            </FieldGrid>
            {project?.embeddings
              && state.embeddings !== undefined
              && state.embeddings !== project.embeddings && (
                <Alert severity="warning" variant="outlined">
                  <strong>Embedding change detected.</strong> Switching from{" "}
                  <Box component="code" sx={{ fontFamily: FONT_MONO }}>{project.embeddings || "(none)"}</Box>{" "}
                  to <Box component="code" sx={{ fontFamily: FONT_MONO }}>{state.embeddings || "(none)"}</Box>{" "}
                  will <strong>discard all previously-computed embeddings</strong> for this project — the
                  conversation memory index is wiped and rebuilt on the next cron tick
                  {state.type === "rag" && ", and the RAG knowledge base will need to be re-ingested before retrieval works again"}.
                </Alert>
              )}
          </Section>
        )}

        {/* ── AGENT LOOP (agent only) ───────────────────────── */}
        {state.type === "agent" && (
          <Section accent={LOOP_ACCENT}>
            <SectionHeader
              title="Agent Loop"
              accent={LOOP_ACCENT}
              subtitle="Underlying agent runtime. 'RESTai' is our in-house loop and works with any platform LLM. 'Claude SDK' drives the Anthropic Claude Agent SDK directly — requires an Anthropic-class LLM. 'LlamaIndex' drops to the upstream llama-index AgentWorkflow — works with any platform LLM. 'smolagents' uses HuggingFace's ToolCallingAgent — talks directly to OpenAI-compatible endpoints (OpenAI, Ollama, vLLM, Grok, Azure); only Anthropic / Gemini / Bedrock go through a LiteLLM fallback. 'OpenAI SDK' drives the OpenAI Agents SDK directly — requires an OpenAI-class LLM."
            />
            <TextField
              select
              fullWidth size="small"
              InputLabelProps={{ shrink: true }}
              label="Agent Loop"
              value={opts.agent_loop || "restai"}
              onChange={(e) => setState({ ...state, options: { ...state.options, agent_loop: e.target.value } })}
            >
              <MenuItem value="restai">RESTai (default — works with any LLM)</MenuItem>
              <MenuItem value="claude">Claude SDK (requires Anthropic LLM)</MenuItem>
              <MenuItem value="llamaindex">LlamaIndex (upstream AgentWorkflow — any LLM)</MenuItem>
              <MenuItem value="smolagents">smolagents (HuggingFace — most LLMs)</MenuItem>
              <MenuItem value="openai_agents">OpenAI SDK (requires OpenAI LLM)</MenuItem>
            </TextField>
          </Section>
        )}

        {/* ── MEMORY (agent only) ───────────────────────────── */}
        {state.type === "agent" && (
          <Section accent={MEM_ACCENT}>
            <SectionHeader
              title="Memory"
              accent={MEM_ACCENT}
              subtitle="Bank: a shared summary prepended to every chat. Search: per-turn vector index for `search_memories` tool."
            />
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
              <FormControlLabel
                label={<span>Memory Bank<HelpTip text="Aggregates summaries of every conversation in this project into a shared memory injected into every chat's system prompt" /></span>}
                control={<Switch checked={opts.memory_bank_enabled ?? false} name="memory_bank_enabled" onChange={handleChange} />}
              />
              <FormControlLabel
                label={<span>Memory Search<HelpTip text="Indexes every conversation turn into a per-project vector collection so the `search_memories` builtin can semantically retrieve past Q/A. Requires an embedding configured on the project." /></span>}
                control={<Switch checked={opts.memory_search_enabled ?? false} name="memory_search_enabled" onChange={handleChange} />}
              />
            </Box>
            {opts.memory_bank_enabled && (
              <TextField
                fullWidth size="small"
                type="number"
                name="memory_bank_max_tokens"
                label={t("projects.edit.general.memoryBankMaxTokens")}
                value={opts.memory_bank_max_tokens ?? 2000}
                inputProps={{ min: 200, max: 10000, step: 100 }}
                onChange={(e) => { clearFieldError("memory_bank_max_tokens"); handleChange(e); }}
                error={!!errorFor("memory_bank_max_tokens")}
                helperText={errorFor("memory_bank_max_tokens") || "Token budget for the injected memory block (200–10000). Older entries get rolled up automatically."}
              />
            )}
            {opts.memory_bank_enabled && (
              <Alert severity="warning" variant="outlined">
                <strong>Privacy notice.</strong> The Memory Bank shares a compressed summary of every conversation in this project with every other conversation. Any user with access to this project will see the agent reference summarized context derived from other users' chats. Do not enable for projects that handle confidential per-user data.
              </Alert>
            )}
            {opts.memory_search_enabled && !state.embeddings && (
              <Alert severity="warning" variant="outlined">
                <strong>Embedding required.</strong> Memory Search needs an embedding configured on this project to index conversations. Pick one in the Embeddings field above, otherwise the indexer will skip every tick and the <code>search_memories</code> tool will return an error when called.
              </Alert>
            )}
            {opts.memory_search_enabled && (
              <Alert severity="warning" variant="outlined">
                <strong>Privacy notice.</strong> Memory Search makes the full conversation history of every user retrievable to every other user with access to this project. Do not enable for projects that handle confidential per-user data.
              </Alert>
            )}
          </Section>
        )}

        {/* ── AGENTIC BROWSER (agent only) ──────────────────── */}
        {state.type === "agent" && (
          <Section accent={BROWSER_ACCENT}>
            <SectionHeader
              title="Agentic Browser"
              accent={BROWSER_ACCENT}
              subtitle="Controls for browser_* builtin tools. Admin must also enable globally in Settings → Agentic Browser."
            />
            <TextField
              fullWidth size="small"
              multiline minRows={2}
              name="browser_allowed_domains"
              label={t("projects.edit.general.browserAllowedDomains")}
              value={opts.browser_allowed_domains ?? ""}
              onChange={(e) => setState({ ...state, options: { ...state.options, browser_allowed_domains: e.target.value } })}
              placeholder="acme.com, *.supplier.net, gov.co.uk"
              helperText="Comma-separated allowlist for browser_goto. Empty = unrestricted (risky — prompt injection can navigate anywhere). Use suffix globs like `*.example.com`."
              InputProps={{ sx: { fontFamily: FONT_MONO } }}
            />
            <FormControlLabel
              label={
                <span>
                  Allow <Box component="code" sx={{ fontFamily: FONT_MONO }}>browser_eval</Box>
                  <HelpTip text="Lets the agent run arbitrary JavaScript in the page. Dangerous — a prompt-injected page can exfiltrate cookies or hit authed APIs. Off by default." />
                </span>
              }
              control={<Switch checked={opts.browser_allow_eval ?? false} name="browser_allow_eval" onChange={handleChange} />}
            />
          </Section>
        )}

      </Box>
    </ContentCard>
  );
}
