import { useState } from "react";
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, TextField, Typography,
} from "@mui/material";
import { AutoAwesome, Description, History } from "@mui/icons-material";
import { useTranslation } from "react-i18next";
import { toast } from "react-toastify";
import api from "app/utils/api";
import useAuth from "app/hooks/useAuth";
import ContentCard from "app/components/page/ContentCard";
import { FONT_MONO } from "app/components/page/pageStyles";
import { SectionHeader, sectionLabelSx, sectionShellSx } from "./integrationsKit";

const ACCENT = "#8b5cf6";

const PRESETS = [
  { key: "general",   label: "General assistant",  prompt: "You are a helpful assistant. Answer questions clearly and concisely." },
  { key: "describe",  label: "Describe image",     prompt: "Describe the provided image in detail. Include colors, objects, people, text, and any notable features." },
  { key: "summarize", label: "Summarize text",     prompt: "Summarize the following text. Keep the summary concise while preserving the key points and main ideas." },
  { key: "translate", label: "Translate to EN",    prompt: "You are a translator. Translate the user's input to English. Preserve the original meaning and tone." },
  { key: "extract",   label: "Extract data (JSON)", prompt: "Extract structured data from the user's input. Return the result as valid JSON." },
  { key: "code",      label: "Code assistant",     prompt: "You are a code assistant. Help the user write, debug, and explain code. Use markdown code blocks in your responses." },
];

function Section({ accent, children }) {
  return (
    <Box sx={{ ...sectionShellSx(accent), p: 2.5, display: "flex", flexDirection: "column", gap: 2 }}>
      {children}
    </Box>
  );
}

export default function ProjectEditSystemPrompt({
  state, setState, project, info,
  promptVersions = [], showVersions, setShowVersions,
}) {
  const { t } = useTranslation();
  const auth = useAuth();
  const [aiOpen, setAiOpen] = useState(false);
  const [aiDescription, setAiDescription] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const generate = () => {
    if (!aiDescription.trim()) return;
    setAiLoading(true);
    api.post(
      `/projects/${project.id}/system-prompt/generate`,
      { description: aiDescription, project_type: state.type || project.type },
      auth.user.token,
    )
      .then((d) => {
        setState((prev) => ({ ...prev, system: d.system_prompt || "" }));
        toast.success(t("projects.edit.systemPrompt.generated", "System prompt generated"));
        setAiOpen(false);
        setAiDescription("");
      })
      .catch(() => {})
      .finally(() => setAiLoading(false));
  };

  const charCount = (state.system || "").length;
  const live = charCount > 0;

  return (
    <ContentCard
      icon={<Description />}
      title={t("projects.edit.systemPrompt.title", "System Message")}
      subtitle={`PROJECT/${String(project?.id ?? 0).padStart(4, "0")} · PROMPT · VERSIONS · AI ASSIST`}
    >
      <Box sx={{ display: "flex", flexDirection: "column", gap: 3 }}>

        {/* ── PROMPT ─────────────────────────────────────────── */}
        <Section accent={ACCENT}>
          <SectionHeader
            title={t("projects.edit.systemPrompt.section.prompt", "Prompt")}
            accent={ACCENT}
            subtitle={`${charCount.toLocaleString()} ${t("projects.edit.systemPrompt.chars", "chars")}`}
            right={
              info?.system_llm_configured && (
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<AutoAwesome />}
                  onClick={() => setAiOpen(true)}
                >
                  {t("projects.edit.systemPrompt.generateAi", "Generate with AI")}
                </Button>
              )
            }
          />
          <Typography sx={{ fontSize: "0.78rem", color: "text.secondary" }}>
            {t("projects.edit.systemPrompt.help",
              "Defines the AI's behavior and personality. Prepended to every conversation.")}
          </Typography>

          <Box>
            <Box sx={{ ...sectionLabelSx, mb: 0.75 }}>
              {t("projects.edit.systemPrompt.section.presets", "Presets")}
            </Box>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
              {PRESETS.map((p) => (
                <Chip
                  key={p.key}
                  label={p.label}
                  variant="outlined"
                  size="small"
                  onClick={() => setState({ ...state, system: p.prompt })}
                  sx={{
                    fontFamily: FONT_MONO,
                    fontSize: "0.7rem",
                    cursor: "pointer",
                    borderRadius: 1,
                    "&:hover": { borderColor: ACCENT, color: ACCENT },
                  }}
                />
              ))}
            </Box>
          </Box>

          <TextField
            fullWidth
            multiline
            minRows={6}
            maxRows={20}
            name="system"
            value={state.system ?? ""}
            onChange={(e) => setState({ ...state, system: e.target.value })}
            placeholder={t("projects.edit.systemPrompt.placeholder",
              "Describe the assistant's role, tone, constraints, and any tools it should prefer…")}
            InputProps={{
              sx: {
                fontFamily: FONT_MONO,
                fontSize: "0.85rem",
                lineHeight: 1.55,
                backgroundColor: "#fafbfc",
              },
            }}
          />
        </Section>

        {/* ── VERSION HISTORY ────────────────────────────────── */}
        {promptVersions.length > 0 && (
          <Section accent="#0ea5e9">
            <SectionHeader
              title={t("projects.edit.systemPrompt.section.versions", "Version history")}
              accent="#0ea5e9"
              subtitle={`${promptVersions.length} ${t("projects.edit.systemPrompt.versions", "versions")}`}
              right={
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<History />}
                  onClick={() => setShowVersions && setShowVersions(!showVersions)}
                >
                  {showVersions
                    ? t("projects.edit.systemPrompt.hide", "Hide")
                    : t("projects.edit.systemPrompt.show", "Show")}
                </Button>
              }
            />
            {showVersions && (
              <Box sx={{
                borderRadius: 1.5,
                border: "1px solid rgba(15,23,42,0.08)",
                backgroundColor: "#fff",
                maxHeight: 360,
                overflow: "auto",
              }}>
                {promptVersions.map((v) => (
                  <Box
                    key={v.id}
                    sx={{
                      p: 1.25,
                      borderBottom: "1px solid rgba(15,23,42,0.05)",
                      display: "flex",
                      gap: 1.5,
                      alignItems: "flex-start",
                      backgroundColor: v.is_active ? "rgba(14,165,233,0.05)" : "transparent",
                      "&:last-of-type": { borderBottom: 0 },
                    }}
                  >
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.25 }}>
                        <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem", fontWeight: 700 }}>
                          v{v.version}
                        </Box>
                        {v.is_active && (
                          <Chip
                            label={t("projects.edit.systemPrompt.active", "active")}
                            size="small"
                            sx={{
                              height: 18, fontSize: "0.62rem", fontFamily: FONT_MONO, fontWeight: 700,
                              backgroundColor: "rgba(14,165,233,0.12)", color: "#0369a1",
                            }}
                          />
                        )}
                        <Box component="span" sx={{ fontFamily: FONT_MONO, fontSize: "0.68rem", color: "text.disabled" }}>
                          {v.created_at ? new Date(v.created_at).toLocaleString() : ""}
                        </Box>
                      </Box>
                      <Typography sx={{
                        fontSize: "0.78rem",
                        color: "text.secondary",
                        lineHeight: 1.45,
                        whiteSpace: "pre-wrap",
                        wordBreak: "break-word",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}>
                        {v.system_prompt || "(empty)"}
                      </Typography>
                    </Box>
                    {!v.is_active && (
                      <Button
                        size="small"
                        variant="outlined"
                        sx={{ minWidth: 80, mt: 0.25 }}
                        onClick={() => setState({ ...state, system: v.system_prompt })}
                      >
                        {t("projects.edit.systemPrompt.restore", "Restore")}
                      </Button>
                    )}
                  </Box>
                ))}
              </Box>
            )}
          </Section>
        )}

        {/* ── CENSORSHIP ─────────────────────────────────────── */}
        <Section accent="#f59e0b">
          <SectionHeader
            title={t("projects.edit.systemPrompt.section.censorship", "Censorship fallback")}
            accent="#f59e0b"
            subtitle={t("projects.edit.systemPrompt.censorshipHelp",
              "Returned verbatim when the model refuses or trips a guard.")}
          />
          <TextField
            fullWidth
            multiline
            minRows={2}
            name="default_prompt"
            value={state.default_prompt ?? ""}
            onChange={(e) => setState({ ...state, default_prompt: e.target.value })}
            placeholder={t("projects.edit.systemPrompt.censorshipPlaceholder",
              "Sorry, I can't help with that.")}
            InputProps={{
              sx: { fontFamily: FONT_MONO, fontSize: "0.85rem", backgroundColor: "#fafbfc" },
            }}
          />
        </Section>

      </Box>

      <Dialog open={aiOpen} onClose={() => !aiLoading && setAiOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{t("projects.edit.systemPrompt.aiTitle", "Generate system prompt with AI")}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t("projects.edit.systemPrompt.aiHelp",
              "Describe in plain English what this project does. The system LLM will draft a full system prompt you can then edit.")}
          </Typography>
          <TextField
            autoFocus
            fullWidth
            multiline
            minRows={3}
            placeholder={'e.g. "customer support assistant for my SaaS billing product"'}
            value={aiDescription}
            onChange={(e) => setAiDescription(e.target.value)}
            disabled={aiLoading}
          />
          <Alert severity="info" sx={{ mt: 2 }}>
            {t("projects.edit.systemPrompt.aiWarn",
              "This replaces the current system message. Copy the existing one first if you want to keep it.")}
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAiOpen(false)} disabled={aiLoading}>
            {t("common.cancel", "Cancel")}
          </Button>
          <Button
            variant="contained"
            onClick={generate}
            disabled={aiLoading || !aiDescription.trim()}
            startIcon={aiLoading ? <CircularProgress size={16} /> : <AutoAwesome />}
          >
            {aiLoading
              ? t("projects.edit.systemPrompt.generating", "Generating…")
              : t("projects.edit.systemPrompt.generate", "Generate")}
          </Button>
        </DialogActions>
      </Dialog>
    </ContentCard>
  );
}
