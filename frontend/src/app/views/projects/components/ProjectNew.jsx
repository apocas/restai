import { useState, useEffect, useMemo } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import {
  Alert, Box, Button, Card, CircularProgress, Grid, InputAdornment,
  MenuItem, TextField, Typography, styled,
} from "@mui/material";
import {
  Memory, Cloud, Lock, Public, AttachMoney, Token, Storage, DataArray,
  Hub, Title, Groups, Save, AutoAwesome, SmartToy, Engineering,
  Apps, Code, MemoryRounded, AddCircle,
} from "@mui/icons-material";
import api from "app/utils/api";
import { usePlatformCapabilities } from "app/contexts/PlatformContext";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";

// Sky-700 page accent — same family as project info.
const ACCENT = "#0284c7";
const ACCENT_DARK = "#0369a1";
const ACCENT_SOFT = "rgba(2,132,199,0.10)";

// Per-type metadata: icon, headline, blurb. Reuses the same colour map
// as the project library / dashboard so the visual identity carries.
const TYPE_META = {
  agent: {
    Icon: SmartToy,
    headline: "Agent",
    blurb: "Direct LLM chat. Optionally attach builtin tools or MCP servers in the Tools tab to turn it into a tool-using agent. The most common project type.",
  },
  rag: {
    Icon: AutoAwesome,
    headline: "RAG",
    blurb: "Retrieval-Augmented Generation. Interact with your own knowledge base fed by uploaded documents.",
  },
  block: {
    Icon: Engineering,
    headline: "Block",
    blurb: "Visual logic builder. Chain projects with a graphical block-based IDE. No LLM required.",
  },
  app: {
    Icon: Apps,
    headline: "App",
    blurb: "Describe an app and the LLM scaffolds a vanilla TypeScript + PHP + SQLite project. In-browser IDE with live preview, deployable via FTP/SFTP or ZIP.",
  },
};

const TileCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent = ACCENT }) => ({
  position: "relative",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "border-color 0.25s ease, box-shadow 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    pointerEvents: "none",
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    borderColor: `${accent}55`,
    boxShadow: `0 18px 36px ${accent}1c, 0 4px 10px rgba(15,23,42,0.05)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

function TileHeader({ icon, title, subtitle, accent = ACCENT, action }) {
  return (
    <Box
      sx={{
        px: 2.5, pt: 2, pb: 1.75,
        display: "flex",
        alignItems: "center",
        gap: 1.5,
        borderBottom: "1px solid rgba(15,23,42,0.06)",
        flexWrap: "wrap",
      }}
    >
      <Box
        sx={{
          width: 36, height: 36, flexShrink: 0,
          borderRadius: 1.5,
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          background: `${accent}1a`,
          color: accent,
          "& svg": { fontSize: 20 },
        }}
      >
        {icon}
      </Box>
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.72rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: accent,
            lineHeight: 1,
          }}
        >
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.4 }}>
            {subtitle}
          </Typography>
        )}
      </Box>
      {action}
    </Box>
  );
}

const fieldSx = {
  "& .MuiOutlinedInput-root": {
    "& fieldset": { borderColor: "rgba(15,23,42,0.12)" },
    "&:hover fieldset": { borderColor: `${ACCENT}55` },
    "&.Mui-focused fieldset": { borderColor: ACCENT, borderWidth: 1.5 },
  },
  "& .MuiInputLabel-root.Mui-focused": { color: ACCENT },
};

// Type tile — clickable card showing the project type's icon, headline,
// and blurb. Coloured accent per type from PROJECT_TYPE_COLORS.
function TypeTile({ type, selected, disabled, onClick }) {
  const meta = TYPE_META[type];
  const colour = PROJECT_TYPE_COLORS[type]?.color || ACCENT;
  if (!meta) return null;
  const Icon = meta.Icon;
  return (
    <Box
      onClick={disabled ? undefined : onClick}
      sx={{
        position: "relative",
        p: 1.5,
        borderRadius: 1.5,
        cursor: disabled ? "not-allowed" : "pointer",
        border: `1px solid ${selected ? colour : "rgba(15,23,42,0.10)"}`,
        backgroundColor: selected ? `${colour}10` : "#ffffff",
        opacity: disabled ? 0.45 : 1,
        transition: "all 160ms ease",
        "&:hover": disabled ? {} : {
          borderColor: `${colour}88`,
          backgroundColor: `${colour}08`,
          transform: "translateY(-1px)",
        },
        "&::before": {
          content: '""',
          position: "absolute",
          left: 0, top: 0, bottom: 0,
          width: 3,
          background: colour,
          opacity: selected ? 1 : 0,
          transition: "opacity 160ms",
        },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.25 }}>
        <Box
          sx={{
            width: 32, height: 32, flexShrink: 0,
            borderRadius: 1.25,
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            background: `linear-gradient(135deg, ${colour}25, ${colour}10)`,
            border: `1px solid ${colour}33`,
            color: colour,
          }}
        >
          <Icon sx={{ fontSize: 18 }} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "0.74rem",
              fontWeight: 800,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: colour,
              lineHeight: 1,
            }}
          >
            {meta.headline}
          </Box>
          <Box
            component="span"
            sx={{
              display: "block",
              fontFamily: FONT_MONO,
              fontSize: "0.6rem",
              color: "text.disabled",
              letterSpacing: "0.04em",
              mt: 0.25,
            }}
          >
            {type}
          </Box>
        </Box>
      </Box>
    </Box>
  );
}

// Live spec card — renders one labelled row for a chosen LLM/embedding/etc.
function SpecBlock({ icon: Icon, title, accent, children }) {
  return (
    <Box
      sx={{
        p: 1.75,
        borderRadius: 1.5,
        border: "1px solid rgba(15,23,42,0.08)",
        backgroundColor: "#fbfdff",
        position: "relative",
        "&::before": {
          content: '""',
          position: "absolute",
          left: 0, top: 0, bottom: 0,
          width: 3,
          background: accent,
          opacity: 0.6,
          borderRadius: "0 0 0 6px",
        },
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mb: 1 }}>
        <Icon sx={{ fontSize: 14, color: accent }} />
        <Box
          component="span"
          sx={{
            fontFamily: FONT_MONO,
            fontSize: "0.62rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            fontWeight: 800,
            color: accent,
          }}
        >
          {title}
        </Box>
      </Box>
      {children}
    </Box>
  );
}

function MonoPill({ value, color = ACCENT, icon: Icon }) {
  return (
    <Box
      sx={{
        display: "inline-flex",
        alignItems: "center",
        gap: 0.4,
        px: 0.7, py: 0.25,
        borderRadius: 0.75,
        backgroundColor: `${color}10`,
        border: `1px solid ${color}33`,
        fontFamily: FONT_MONO,
        fontSize: "0.66rem",
        fontWeight: 700,
        color,
      }}
    >
      {Icon && <Icon sx={{ fontSize: 11 }} />}
      {value}
    </Box>
  );
}

export default function ProjectNew({ info, template }) {
  const { platformCapabilities } = usePlatformCapabilities();
  const typeList = ["agent", "rag", "block", ...(platformCapabilities?.app_builder ? ["app"] : [])];
  const vectorstoreList = info.vectorstores || ["chroma"];
  const auth = useAuth();
  const navigate = useNavigate();

  const [state, setState] = useState({});
  const [teams, setTeams] = useState([]);
  const [selectedTeam, setSelectedTeam] = useState(null);
  const [teamLLMs, setTeamLLMs] = useState([]);
  const [teamEmbeddings, setTeamEmbeddings] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    api.get("/teams", auth.user.token)
      .then((d) => setTeams(d.teams || []))
      .catch(() => {});
    if (template) {
      setState((prev) => ({ ...prev, projecttype: template.type }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const fetchTeamDetails = (teamId) => {
    api.get("/teams/" + teamId, auth.user.token)
      .then((team) => {
        setSelectedTeam(team);
        const availableLLMs = team.llms || [];
        const filteredLLMs = info.llms.filter((llm) =>
          availableLLMs.some((teamLLM) => teamLLM.name === llm.name)
        );
        setTeamLLMs(filteredLLMs);

        const availableEmbeddings = team.embeddings || [];
        const filteredEmbeddings = info.embeddings.filter((emb) =>
          availableEmbeddings.some((teamEmb) => teamEmb.name === emb.name)
        );
        setTeamEmbeddings(filteredEmbeddings);

        // Auto-select singletons.
        setState((prev) => ({
          ...prev,
          projectllm: filteredLLMs.length === 1 ? filteredLLMs[0].name : prev.projectllm || "",
          projectembeddings: filteredEmbeddings.length === 1 ? filteredEmbeddings[0].name : prev.projectembeddings || "",
          projectvectorstore: vectorstoreList.length === 1 ? vectorstoreList[0] : prev.projectvectorstore || "",
        }));
      })
      .catch(() => {});
  };

  const handleTeamChange = (e) => {
    const teamId = e.target.value;
    setState({ ...state, team_id: teamId, projectllm: "", projectembeddings: "" });
    if (teamId) fetchTeamDetails(teamId);
    else { setSelectedTeam(null); setTeamLLMs([]); setTeamEmbeddings([]); }
  };

  const handleChange = (e) => {
    if (e?.persist) e.persist();
    setState({ ...state, [e.target.name]: e.target.value });
  };

  const pickType = (t) => {
    if (template) return; // template locks the type
    setState((prev) => ({ ...prev, projecttype: t }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    const opts = { name: state.projectname, type: state.projecttype };
    if (state.projecttype !== "block") opts.llm = state.projectllm;
    if (state.projecttype === "rag") {
      opts.embeddings = state.projectembeddings;
      opts.vectorstore = state.projectvectorstore;
    }
    if (state.team_id) opts.team_id = state.team_id;
    if (template && template.human_description) {
      opts.human_description = template.human_description || template.description;
    }
    try {
      const response = await api.post("/projects", opts, auth.user.token);
      if (template && (template.system || (template.options && Object.keys(template.options).length > 0))) {
        const patchOpts = {};
        if (template.system) patchOpts.system = template.system;
        if (template.options) patchOpts.options = template.options;
        if (template.description) patchOpts.human_description = template.description;
        try { await api.patch("/projects/" + response.project, patchOpts, auth.user.token); } catch {}
      }
      if (state.projecttype === "app") {
        navigate("/project/" + response.project + "/builder");
      } else {
        navigate("/project/" + response.project);
      }
    } catch {} finally { setSubmitting(false); }
  };

  const llmDetail = useMemo(
    () => state.projectllm ? teamLLMs.find((l) => l.name === state.projectllm) : null,
    [state.projectllm, teamLLMs]
  );
  const embDetail = useMemo(
    () => state.projectembeddings ? teamEmbeddings.find((e) => e.name === state.projectembeddings) : null,
    [state.projectembeddings, teamEmbeddings]
  );

  const canSubmit = !!state.projectname && !!state.team_id && !!state.projecttype
    && (state.projecttype === "block" || !!state.projectllm)
    && (state.projecttype !== "rag" || (!!state.projectembeddings && !!state.projectvectorstore));

  return (
    <form onSubmit={handleSubmit}>
      {template && (
        <Alert
          severity="info"
          icon={<AutoAwesome fontSize="small" sx={{ color: ACCENT }} />}
          sx={{
            mb: 2.5,
            borderRadius: 2,
            border: `1px solid ${ACCENT}33`,
            backgroundColor: ACCENT_SOFT,
            color: ACCENT_DARK,
            "& .MuiAlert-icon": { alignItems: "center" },
          }}
        >
          <strong>{template.name}</strong> — {template.description}
          {template.system && (
            <Box
              component="span"
              sx={{
                display: "block",
                mt: 0.5,
                fontFamily: FONT_MONO,
                fontSize: "0.7rem",
                letterSpacing: "0.04em",
                color: "text.secondary",
                fontStyle: "italic",
              }}
            >
              ▸ system prompt and settings will be applied automatically
            </Box>
          )}
        </Alert>
      )}

      <Grid container spacing={2.5}>
        {/* ── LEFT: form ─────────────────────────────────────── */}
        <Grid item xs={12} md={7}>
          <TileCard elevation={0} accent={ACCENT}>
            <TileHeader
              icon={<AddCircle />}
              title={template ? `New from ${template.name}` : "Project setup"}
              subtitle="Identity, team, and runtime"
              accent={ACCENT}
            />
            <Box sx={{ p: 2.5 }}>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <TextField
                    fullWidth
                    name="projectname"
                    label="Project name"
                    value={state.projectname || ""}
                    onChange={handleChange}
                    required
                    InputLabelProps={{ shrink: true }}
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <Title sx={{ fontSize: 18, color: ACCENT }} />
                        </InputAdornment>
                      ),
                    }}
                    sx={fieldSx}
                  />
                </Grid>
                <Grid item xs={12} md={6}>
                  <TextField
                    select
                    fullWidth
                    name="team_id"
                    label="Team"
                    value={state.team_id ?? ""}
                    onChange={handleTeamChange}
                    required
                    helperText="A project belongs to one team"
                    InputLabelProps={{ shrink: true }}
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <Groups sx={{ fontSize: 18, color: "#c026d3" }} />
                        </InputAdornment>
                      ),
                    }}
                    sx={fieldSx}
                  >
                    {teams.length === 0 && (
                      <MenuItem value="" disabled>No teams available</MenuItem>
                    )}
                    {teams.map((team) => (
                      <MenuItem value={team.id} key={team.id}>
                        {team.name}
                      </MenuItem>
                    ))}
                  </TextField>
                </Grid>

                {selectedTeam && (
                  <Grid item xs={12}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 0.75,
                        mb: 1,
                        fontFamily: FONT_MONO,
                        fontSize: "0.62rem",
                        letterSpacing: "0.12em",
                        textTransform: "uppercase",
                        fontWeight: 800,
                        color: "text.secondary",
                      }}
                    >
                      <Box sx={{ width: 12, height: 2, background: ACCENT }} />
                      Type
                    </Box>
                    <Grid container spacing={1.25}>
                      {typeList.map((t) => (
                        <Grid item xs={12} sm={6} md={typeList.length > 3 ? 3 : 4} key={t}>
                          <TypeTile
                            type={t}
                            selected={state.projecttype === t}
                            disabled={!!template && template.type !== t}
                            onClick={() => pickType(t)}
                          />
                        </Grid>
                      ))}
                    </Grid>
                  </Grid>
                )}

                {/* LLM */}
                {selectedTeam && state.projecttype && state.projecttype !== "block" && (
                  <Grid item xs={12} md={state.projecttype === "rag" ? 12 : 12}>
                    <TextField
                      select
                      fullWidth
                      name="projectllm"
                      label="LLM"
                      value={state.projectllm || ""}
                      onChange={handleChange}
                      helperText={teamLLMs.length === 0 ? "No LLMs available for this team" : "Inference engine for this project"}
                      InputLabelProps={{ shrink: true }}
                      InputProps={{
                        startAdornment: (
                          <InputAdornment position="start">
                            <Memory sx={{ fontSize: 18, color: "#0284c7" }} />
                          </InputAdornment>
                        ),
                      }}
                      sx={fieldSx}
                    >
                      {teamLLMs.map((item) => (
                        <MenuItem value={item.name} key={item.name}>
                          <Box sx={{ display: "flex", alignItems: "center", gap: 1, width: "100%" }}>
                            <Box component="span" sx={{ flex: 1 }}>{item.name}</Box>
                            {item.privacy && (
                              <Box
                                component="span"
                                sx={{
                                  fontFamily: FONT_MONO,
                                  fontSize: "0.6rem",
                                  color: "text.disabled",
                                  textTransform: "uppercase",
                                  letterSpacing: "0.04em",
                                }}
                              >
                                {item.class_name}
                              </Box>
                            )}
                          </Box>
                        </MenuItem>
                      ))}
                    </TextField>
                  </Grid>
                )}

                {/* RAG-only fields */}
                {selectedTeam && state.projecttype === "rag" && (
                  <>
                    <Grid item xs={12} md={6}>
                      <TextField
                        select
                        fullWidth
                        name="projectembeddings"
                        label="Embeddings"
                        value={state.projectembeddings || ""}
                        onChange={handleChange}
                        helperText={teamEmbeddings.length === 0 ? "No embeddings available" : "Vector encoder for retrieval"}
                        InputLabelProps={{ shrink: true }}
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Hub sx={{ fontSize: 18, color: "#0d9488" }} />
                            </InputAdornment>
                          ),
                        }}
                        sx={fieldSx}
                      >
                        {teamEmbeddings.map((item) => (
                          <MenuItem value={item.name} key={item.name}>{item.name}</MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                    <Grid item xs={12} md={6}>
                      <TextField
                        select
                        fullWidth
                        name="projectvectorstore"
                        label="Vector store"
                        value={state.projectvectorstore || ""}
                        onChange={handleChange}
                        helperText="Where vector embeddings are stored"
                        InputLabelProps={{ shrink: true }}
                        InputProps={{
                          startAdornment: (
                            <InputAdornment position="start">
                              <Storage sx={{ fontSize: 18, color: "#f59e0b" }} />
                            </InputAdornment>
                          ),
                        }}
                        sx={fieldSx}
                      >
                        {vectorstoreList.map((item) => (
                          <MenuItem value={item} key={item}>{item}</MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                  </>
                )}
              </Grid>
            </Box>

            <Box
              sx={{
                px: 2.5, py: 1.75,
                borderTop: "1px solid rgba(15,23,42,0.06)",
                display: "flex",
                justifyContent: "flex-end",
              }}
            >
              <Button
                type="submit"
                variant="contained"
                disabled={!canSubmit || submitting}
                startIcon={submitting ? <CircularProgress size={14} color="inherit" /> : <Save />}
                sx={{
                  textTransform: "none",
                  fontWeight: 700,
                  background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
                  boxShadow: `0 4px 14px ${ACCENT}55`,
                  "&:hover": {
                    background: `linear-gradient(135deg, ${ACCENT} 0%, #075985 100%)`,
                    boxShadow: `0 6px 18px ${ACCENT}77`,
                  },
                  "&.Mui-disabled": {
                    background: "rgba(15,23,42,0.06)",
                    color: "rgba(15,23,42,0.3)",
                    boxShadow: "none",
                  },
                }}
              >
                {submitting ? "Creating…" : "Create project"}
              </Button>
            </Box>
          </TileCard>
        </Grid>

        {/* ── RIGHT: live spec preview ────────────────────────── */}
        <Grid item xs={12} md={5}>
          <TileCard elevation={0} accent="#0d9488">
            <TileHeader
              icon={<Code />}
              title="Live spec"
              subtitle="What the project will look like"
              accent="#0d9488"
            />
            <Box sx={{ p: 2.5, display: "flex", flexDirection: "column", gap: 1.5 }}>
              {!state.projecttype && !state.projectllm ? (
                <Box
                  sx={{
                    py: 4,
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 1,
                  }}
                >
                  <Box
                    sx={{
                      width: 48, height: 48,
                      borderRadius: "50%",
                      background: "rgba(13,148,136,0.10)",
                      display: "inline-flex",
                      alignItems: "center",
                      justifyContent: "center",
                      animation: `${pulse} 3s ease-out infinite`,
                    }}
                  >
                    <Memory sx={{ fontSize: 22, color: "#0d9488" }} />
                  </Box>
                  <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center" }}>
                    Select options to see the project spec build up
                  </Typography>
                </Box>
              ) : (
                <>
                  {state.projecttype && (
                    <SpecBlock
                      icon={Hub}
                      title="Project type"
                      accent={PROJECT_TYPE_COLORS[state.projecttype]?.color || ACCENT}
                    >
                      <Box sx={{ display: "inline-block" }}>
                        <MonoPill
                          value={state.projecttype.toUpperCase()}
                          color={PROJECT_TYPE_COLORS[state.projecttype]?.color || ACCENT}
                        />
                      </Box>
                      <Typography
                        variant="caption"
                        sx={{ display: "block", mt: 1, color: "text.secondary", lineHeight: 1.45 }}
                      >
                        {TYPE_META[state.projecttype]?.blurb}
                      </Typography>
                    </SpecBlock>
                  )}

                  {llmDetail && (
                    <SpecBlock icon={Memory} title="LLM" accent="#0284c7">
                      <Box
                        component="span"
                        sx={{
                          display: "block",
                          fontFamily: FONT_MONO,
                          fontSize: "0.95rem",
                          fontWeight: 800,
                          color: "text.primary",
                          mb: 0.5,
                        }}
                      >
                        {llmDetail.name}
                      </Box>
                      {llmDetail.description && (
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1, fontSize: "0.78rem" }}>
                          {llmDetail.description}
                        </Typography>
                      )}
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                        <MonoPill icon={Cloud} value={llmDetail.class_name} color="#0284c7" />
                        <MonoPill
                          icon={llmDetail.privacy === "private" ? Lock : Public}
                          value={(llmDetail.privacy || "—").toUpperCase()}
                          color={llmDetail.privacy === "private" ? "#f59e0b" : "#10b981"}
                        />
                        {llmDetail.context_window && (
                          <MonoPill
                            icon={Token}
                            value={`${(llmDetail.context_window / 1000).toFixed(0)}K`}
                            color="#7c3aed"
                          />
                        )}
                      </Box>
                      {(llmDetail.input_cost > 0 || llmDetail.output_cost > 0) && (
                        <Box sx={{ display: "flex", gap: 0.5, mt: 1, flexWrap: "wrap" }}>
                          {llmDetail.input_cost > 0 && (
                            <MonoPill
                              icon={AttachMoney}
                              value={`in ${llmDetail.input_cost}/1K`}
                              color="#0891b2"
                            />
                          )}
                          {llmDetail.output_cost > 0 && (
                            <MonoPill
                              icon={AttachMoney}
                              value={`out ${llmDetail.output_cost}/1K`}
                              color="#0d9488"
                            />
                          )}
                        </Box>
                      )}
                    </SpecBlock>
                  )}

                  {embDetail && (
                    <SpecBlock icon={DataArray} title="Embeddings" accent="#0d9488">
                      <Box
                        component="span"
                        sx={{
                          display: "block",
                          fontFamily: FONT_MONO,
                          fontSize: "0.92rem",
                          fontWeight: 800,
                          color: "text.primary",
                          mb: 0.5,
                        }}
                      >
                        {embDetail.name}
                      </Box>
                      {embDetail.description && (
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 1, fontSize: "0.78rem" }}>
                          {embDetail.description}
                        </Typography>
                      )}
                      <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.5 }}>
                        <MonoPill icon={Cloud} value={embDetail.class_name} color="#0d9488" />
                        <MonoPill
                          icon={embDetail.privacy === "private" ? Lock : Public}
                          value={(embDetail.privacy || "—").toUpperCase()}
                          color={embDetail.privacy === "private" ? "#f59e0b" : "#10b981"}
                        />
                        {embDetail.dimension && (
                          <MonoPill icon={MemoryRounded} value={`${embDetail.dimension}-d`} color="#0891b2" />
                        )}
                      </Box>
                    </SpecBlock>
                  )}

                  {state.projectvectorstore && (
                    <SpecBlock icon={Storage} title="Vector store" accent="#f59e0b">
                      <MonoPill value={state.projectvectorstore.toUpperCase()} color="#f59e0b" icon={Storage} />
                    </SpecBlock>
                  )}

                  {selectedTeam && (
                    <SpecBlock icon={Groups} title="Team" accent="#c026d3">
                      <Box
                        component="span"
                        sx={{
                          display: "block",
                          fontFamily: FONT_MONO,
                          fontSize: "0.88rem",
                          fontWeight: 800,
                          color: "#c026d3",
                        }}
                      >
                        {selectedTeam.name}
                      </Box>
                      <Box sx={{ display: "flex", gap: 0.5, mt: 0.75, flexWrap: "wrap" }}>
                        <MonoPill value={`${(selectedTeam.users || []).length} members`} color="#c026d3" />
                        <MonoPill value={`${(selectedTeam.projects || []).length} projects`} color="#c026d3" />
                      </Box>
                    </SpecBlock>
                  )}
                </>
              )}
            </Box>
          </TileCard>
        </Grid>
      </Grid>

    </form>
  );
}
