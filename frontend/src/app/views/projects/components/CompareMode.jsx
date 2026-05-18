import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import {
  Box, IconButton, MenuItem, Select, TextField, Tooltip, Typography, Fab,
  styled,
} from "@mui/material";
import {
  Send, AttachFile, Close, SwapHoriz, OpenInFull, CloseFullscreen, Lock,
} from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import ChatPanel from "./ChatPanel";
import { FONT_MONO, pulse, sweep } from "app/components/page/pageStyles";

const HiddenInput = styled("input")({ display: "none" });

// Two-panel palette — A is cyan, B is violet. Picked so they read as
// peer color-coded lanes (not "primary vs secondary") and never share
// hue with the playground's lane theme (output is navy, thoughts purple,
// tools cyan — keeping these slightly different so a side-by-side
// comparison doesn't visually fuse with the lane chrome).
const RIG_THEME = {
  A: { accent: "#0e7490", soft: "rgba(14,116,144,0.08)", glow: "rgba(14,116,144,0.18)", label: "RIG · A" },
  B: { accent: "#7c3aed", soft: "rgba(124,58,237,0.08)", glow: "rgba(124,58,237,0.18)", label: "RIG · B" },
};

const Rig = styled(Box, { shouldForwardProp: (p) => p !== "accent" })(
  ({ accent }) => ({
    position: "relative",
    flex: 1,
    minWidth: 0,
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
    background: "#ffffff",
    borderRadius: 14,
    border: "1px solid rgba(15,23,42,0.08)",
    overflow: "hidden",
    transition: "border-color 0.25s ease, box-shadow 0.25s ease",
    // Left accent rail — the visual hook telling you which rig is which.
    "&::before": {
      content: '""',
      position: "absolute",
      left: 0, top: 0, bottom: 0,
      width: 4,
      background: accent,
      opacity: 0.9,
      zIndex: 2,
    },
    "&::after": {
      content: '""',
      position: "absolute",
      left: 0, right: 0, top: 0, height: 3,
      background: `linear-gradient(90deg, transparent, ${accent}33, transparent)`,
      transform: "translateX(-100%)",
      opacity: 0,
      pointerEvents: "none",
      animation: `${sweep} 7s ease-in-out infinite`,
    },
    "&:hover": {
      borderColor: `${accent}55`,
      boxShadow: `0 12px 24px ${accent}1a`,
    },
  })
);

const RigHeader = styled(Box, { shouldForwardProp: (p) => p !== "accent" })(
  ({ accent }) => ({
    flex: "0 0 auto",
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 12px 10px 18px",
    background: "linear-gradient(180deg, rgba(15,23,42,0.02) 0%, transparent 100%)",
    borderBottom: "1px solid rgba(15,23,42,0.06)",
    "& .rig-tag": {
      fontFamily: FONT_MONO,
      fontSize: "0.62rem",
      letterSpacing: "0.2em",
      fontWeight: 800,
      color: accent,
      textTransform: "uppercase",
    },
  })
);

const VersionSelect = styled(Select, { shouldForwardProp: (p) => p !== "accent" })(
  ({ accent }) => ({
    flex: 1,
    minWidth: 0,
    fontFamily: FONT_MONO,
    fontSize: "0.74rem",
    fontWeight: 600,
    color: "#0f172a",
    background: "#fff",
    "& .MuiSelect-select": { padding: "5px 28px 5px 10px" },
    "& fieldset": { borderColor: "rgba(15,23,42,0.12)" },
    "&:hover fieldset": { borderColor: `${accent}88 !important` },
    "&.Mui-focused fieldset": { borderColor: `${accent} !important`, borderWidth: "1px !important" },
  })
);

// Compact preview of the selected prompt so the user knows what's
// running before they hit fire. Click the OpenInFull icon to pop a
// full-text modal-less expander. Single-line truncation by default,
// expanded shows the full prompt under the header.
function PromptPreview({ text, accent, expanded, onToggle }) {
  if (!text) {
    return (
      <Box sx={{
        px: 1.5, py: 1, mt: 0.5,
        background: "rgba(15,23,42,0.03)",
        borderRadius: 1,
        border: "1px dashed rgba(15,23,42,0.12)",
      }}>
        <Typography sx={{
          fontFamily: FONT_MONO, fontSize: "0.66rem",
          color: "rgba(15,23,42,0.4)", letterSpacing: "0.1em",
          textTransform: "uppercase",
        }}>
          empty system prompt
        </Typography>
      </Box>
    );
  }
  return (
    <Box
      sx={{
        px: 1.5, py: 0.75, mt: 0.5,
        position: "relative",
        background: "rgba(15,23,42,0.025)",
        borderRadius: 1,
        border: `1px solid ${accent}1f`,
        borderLeft: `3px solid ${accent}`,
        cursor: "pointer",
      }}
      onClick={onToggle}
    >
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.75 }}>
        <Typography
          sx={{
            flex: 1,
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
            color: "rgba(15,23,42,0.7)",
            whiteSpace: expanded ? "pre-wrap" : "nowrap",
            overflow: expanded ? "visible" : "hidden",
            textOverflow: expanded ? "clip" : "ellipsis",
            maxHeight: expanded ? 220 : "1.5em",
            lineHeight: 1.5,
            transition: "max-height 0.2s ease",
          }}
        >
          {text}
        </Typography>
        <Box sx={{ display: "flex", alignItems: "center", color: accent, opacity: 0.7 }}>
          {expanded ? <CloseFullscreen sx={{ fontSize: 13 }} /> : <OpenInFull sx={{ fontSize: 13 }} />}
        </Box>
      </Box>
    </Box>
  );
}

export default function CompareMode({ project }) {
  const auth = useAuth();
  const [versions, setVersions] = useState([]);
  const [selectedA, setSelectedA] = useState("");
  const [selectedB, setSelectedB] = useState("");
  const [sharedInput, setSharedInput] = useState("");
  const [sharedFiles, setSharedFiles] = useState([]);
  const [questionA, setQuestionA] = useState(null);
  const [questionB, setQuestionB] = useState(null);
  const [counter, setCounter] = useState(0);
  const [expandedA, setExpandedA] = useState(false);
  const [expandedB, setExpandedB] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    api.get(`/projects/${project.id}/prompts`, auth.user.token, { silent: true })
      .then((data) => {
        const list = Array.isArray(data) ? data : [];
        setVersions(list);
        const active = list.find((v) => v.is_active);
        if (active) {
          setSelectedA(active.id);
          const other = list.find((v) => v.id !== active.id);
          if (other) setSelectedB(other.id);
        } else if (list.length > 0) {
          setSelectedA(list[0].id);
          if (list[1]) setSelectedB(list[1].id);
        }
      })
      .catch(() => {});
  }, [project.id, auth.user.token]);

  const versionMap = useMemo(() => {
    const m = new Map();
    versions.forEach((v) => m.set(v.id, v));
    return m;
  }, [versions]);

  const getPrompt = useCallback((id) => versionMap.get(id)?.system_prompt || "", [versionMap]);
  const getVersionNumber = useCallback((id) => versionMap.get(id)?.version, [versionMap]);
  const isActiveVersion = useCallback((id) => !!versionMap.get(id)?.is_active, [versionMap]);

  const handleSwap = () => {
    setSelectedA(selectedB);
    setSelectedB(selectedA);
  };

  const handleSend = () => {
    const text = sharedInput.trim();
    if (!text && sharedFiles.length === 0) return;
    if (!selectedA || !selectedB) return;
    const c = counter + 1;
    setCounter(c);
    // sharedQuestion props are read once each time their `ts` changes;
    // ChatPanel's effect fires on truthy `sharedQuestion.text` (or image).
    // We map sharedFiles → the same shape ChatPanel uses.
    const attach = sharedFiles.length
      ? { image: sharedFiles[0].dataUrl /* legacy single-image shape */ }
      : {};
    setQuestionA({ text, ts: c, ...attach });
    setQuestionB({ text, ts: c, ...attach });
    setSharedInput("");
    setSharedFiles([]);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
      e.preventDefault();
      handleSend();
    }
  };

  const fileIsImage = (file) => {
    const t = (file.type || "").toLowerCase();
    if (t.startsWith("image/")) return true;
    return /\.(png|jpe?g|gif|webp|bmp|svg)$/.test((file.name || "").toLowerCase());
  };

  const handleFiles = async (e) => {
    const chosen = Array.from(e.target.files || []);
    e.target.value = "";
    if (!chosen.length) return;
    const accepted = [];
    for (const file of chosen.slice(0, 5)) {
      if (file.size > 20 * 1024 * 1024) continue;
      const dataUrl = await new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result || "");
        r.onerror = rej;
        r.readAsDataURL(file);
      });
      accepted.push({ name: file.name, size: file.size, mime_type: file.type, dataUrl, isImage: fileIsImage(file) });
    }
    if (accepted.length) setSharedFiles((p) => [...p, ...accepted]);
  };

  if (versions.length < 1) {
    return (
      <Box sx={{
        textAlign: "center", py: 8, px: 3,
        color: "text.secondary",
        maxWidth: 480, mx: "auto",
      }}>
        <Typography sx={{
          fontFamily: FONT_MONO, fontSize: "0.68rem",
          letterSpacing: "0.2em", fontWeight: 700,
          color: "rgba(15,23,42,0.45)", mb: 1.5,
          textTransform: "uppercase",
        }}>
          no prompt versions yet
        </Typography>
        <Typography variant="body2" sx={{ color: "rgba(15,23,42,0.55)" }}>
          Edit and save the project's system message to create the first version. Each save mints a new comparable revision.
        </Typography>
      </Box>
    );
  }

  const aActive = isActiveVersion(selectedA);
  const bActive = isActiveVersion(selectedB);
  const sameVersion = selectedA && selectedB && selectedA === selectedB;
  const canFire = !!selectedA && !!selectedB && (sharedInput.trim().length > 0 || sharedFiles.length > 0);

  return (
    <Box sx={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      gap: 1.5,
    }}>
      {/* Two parallel rigs */}
      <Box sx={{
        flex: 1, minHeight: 0,
        display: "flex",
        gap: 1.5,
        position: "relative",
      }}>
        {/* Center swap chevron — sits in the gutter between the two rigs */}
        <Tooltip title="Swap A ↔ B">
          <IconButton
            size="small"
            onClick={handleSwap}
            disabled={!selectedA || !selectedB}
            sx={{
              position: "absolute",
              left: "50%",
              top: 14,
              transform: "translateX(-50%)",
              zIndex: 5,
              width: 28, height: 28,
              background: "#fff",
              border: "1px solid rgba(15,23,42,0.12)",
              color: "rgba(15,23,42,0.55)",
              "&:hover": { background: "#fff", color: "#0f172a", boxShadow: "0 4px 10px rgba(15,23,42,0.08)" },
            }}
          >
            <SwapHoriz sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>

        {["A", "B"].map((side) => {
          const id = side === "A" ? selectedA : selectedB;
          const setId = side === "A" ? setSelectedA : setSelectedB;
          const expanded = side === "A" ? expandedA : expandedB;
          const setExpanded = side === "A" ? setExpandedA : setExpandedB;
          const theme = RIG_THEME[side];
          const versionNum = getVersionNumber(id);
          const active = side === "A" ? aActive : bActive;
          return (
            <Rig key={side} accent={theme.accent}>
              <RigHeader accent={theme.accent}>
                <Box className="rig-tag">{theme.label}</Box>
                {versionNum != null && (
                  <Box
                    sx={{
                      fontFamily: FONT_MONO,
                      fontSize: "0.76rem",
                      fontWeight: 800,
                      color: "#0f172a",
                      px: 0.75, py: 0.1,
                      background: theme.soft,
                      borderRadius: 0.75,
                    }}
                  >
                    v{versionNum}
                  </Box>
                )}
                {active && (
                  <Box sx={{
                    fontFamily: FONT_MONO, fontSize: "0.58rem",
                    letterSpacing: "0.18em", fontWeight: 700,
                    color: "#16a34a",
                    display: "flex", alignItems: "center", gap: 0.4,
                  }}>
                    <Box sx={{
                      width: 6, height: 6, borderRadius: "50%",
                      background: "#16a34a",
                      boxShadow: "0 0 6px #16a34a",
                      animation: `${pulse} 2.4s ease-out infinite`,
                    }} />
                    LIVE
                  </Box>
                )}
                <Box sx={{ flex: 1 }} />
                <VersionSelect
                  size="small"
                  value={id || ""}
                  onChange={(e) => setId(e.target.value)}
                  accent={theme.accent}
                  displayEmpty
                  renderValue={(v) => {
                    if (!v) return <span style={{ opacity: 0.5 }}>Select version</span>;
                    const ver = versionMap.get(v);
                    if (!ver) return "—";
                    return `v${ver.version}${ver.is_active ? " · active" : ""}`;
                  }}
                  sx={{ flex: "0 0 auto", maxWidth: 180 }}
                >
                  {versions.map((v) => (
                    <MenuItem key={v.id} value={v.id} sx={{ fontFamily: FONT_MONO, fontSize: "0.78rem" }}>
                      v{v.version}{v.is_active ? " · active" : ""}
                    </MenuItem>
                  ))}
                </VersionSelect>
              </RigHeader>

              <Box sx={{ px: 1.5, pt: 1, pb: 0 }}>
                <PromptPreview
                  text={getPrompt(id)}
                  accent={theme.accent}
                  expanded={expanded}
                  onToggle={() => setExpanded((x) => !x)}
                />
              </Box>

              <Box sx={{ flex: 1, minHeight: 0, display: "flex", flexDirection: "column" }}>
                <ChatPanel
                  project={project}
                  systemOverride={getPrompt(id)}
                  sharedQuestion={side === "A" ? questionA : questionB}
                  compact
                  hideInput
                />
              </Box>
            </Rig>
          );
        })}
      </Box>

      {/* Optional notice when both panels run the same version. Cheap
          guardrail — comparing v3 against v3 just burns tokens twice. */}
      {sameVersion && (
        <Box sx={{
          flex: "0 0 auto",
          mx: 0.5,
          px: 1.25, py: 0.5,
          borderRadius: 1,
          background: "rgba(245, 158, 11, 0.08)",
          border: "1px solid rgba(245, 158, 11, 0.3)",
          display: "flex", alignItems: "center", gap: 0.75,
        }}>
          <Lock sx={{ fontSize: 13, color: "#b45309" }} />
          <Typography sx={{
            fontFamily: FONT_MONO, fontSize: "0.66rem",
            letterSpacing: "0.08em", color: "#92400e",
          }}>
            Both rigs are running the same prompt version — output will be redundant.
          </Typography>
        </Box>
      )}

      {/* Attachment thumbnails */}
      {sharedFiles.length > 0 && (
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75, px: 0.5 }}>
          {sharedFiles.map((f, i) => (
            f.isImage ? (
              <Box
                key={`${f.name}-${i}`}
                sx={{
                  position: "relative", width: 52, height: 52,
                  borderRadius: 1, overflow: "hidden",
                  border: "1px solid rgba(15,23,42,0.12)",
                }}
              >
                <Box component="img" src={f.dataUrl} alt={f.name}
                  sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
                <IconButton
                  size="small"
                  onClick={() => setSharedFiles((p) => p.filter((_, j) => j !== i))}
                  sx={{
                    position: "absolute", top: 0, right: 0,
                    width: 18, height: 18, p: 0,
                    bgcolor: "rgba(0,0,0,0.6)", color: "#fff",
                    "&:hover": { bgcolor: "rgba(0,0,0,0.8)" },
                  }}
                >
                  <Close sx={{ fontSize: 12 }} />
                </IconButton>
              </Box>
            ) : (
              <Box key={`${f.name}-${i}`} sx={{
                display: "flex", alignItems: "center", gap: 0.5,
                px: 1, py: 0.4,
                border: "1px solid rgba(15,23,42,0.12)",
                borderRadius: 0.75,
                fontFamily: FONT_MONO, fontSize: "0.7rem",
              }}>
                <AttachFile sx={{ fontSize: 13 }} />
                <span>{f.name}</span>
                <IconButton size="small" sx={{ p: 0.25, ml: 0.25 }}
                  onClick={() => setSharedFiles((p) => p.filter((_, j) => j !== i))}>
                  <Close sx={{ fontSize: 12 }} />
                </IconButton>
              </Box>
            )
          ))}
        </Box>
      )}

      {/* Shared firing console — the single input that feeds both rigs */}
      <Box sx={{
        flex: "0 0 auto",
        display: "flex",
        alignItems: "stretch",
        gap: 1.25,
        p: 1.5,
        borderRadius: 1.5,
        background: "linear-gradient(180deg, rgba(15,23,42,0.02), rgba(15,23,42,0))",
        border: "1px solid rgba(15,23,42,0.08)",
      }}>
        {/* Twin lights */}
        <Box sx={{
          display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          gap: 0.5, px: 0.25,
        }}>
          {["A", "B"].map((side) => {
            const id = side === "A" ? selectedA : selectedB;
            return (
              <Box
                key={side}
                sx={{
                  display: "flex", alignItems: "center", gap: 0.5,
                  fontFamily: FONT_MONO, fontSize: "0.58rem",
                  letterSpacing: "0.16em", fontWeight: 700,
                  color: id ? RIG_THEME[side].accent : "rgba(15,23,42,0.3)",
                }}
              >
                <Box sx={{
                  width: 7, height: 7, borderRadius: "50%",
                  background: id ? RIG_THEME[side].accent : "rgba(15,23,42,0.2)",
                  boxShadow: id ? `0 0 8px ${RIG_THEME[side].accent}` : "none",
                }} />
                {side}
              </Box>
            );
          })}
        </Box>

        <TextField
          fullWidth
          size="small"
          placeholder="Type a prompt — fires into both rigs at once…"
          value={sharedInput}
          onChange={(e) => setSharedInput(e.target.value)}
          onKeyDown={handleKeyDown}
          multiline
          maxRows={4}
          InputProps={{
            sx: {
              fontFamily: FONT_MONO, fontSize: "0.82rem",
              background: "#fff",
            },
          }}
        />

        {(project.type === "agent" || project.type === "block") && (
          <>
            <Tooltip title="Attach images / files">
              <label htmlFor={`compare-upload-${project.id}`}>
                <Fab color="default" size="medium" component="span"
                  sx={{ flexShrink: 0, boxShadow: "0 2px 6px rgba(15,23,42,0.08)" }}>
                  <AttachFile fontSize="small" />
                </Fab>
              </label>
            </Tooltip>
            <HiddenInput
              ref={fileInputRef}
              onChange={handleFiles}
              id={`compare-upload-${project.id}`}
              type="file"
              multiple
              accept={project.type === "agent" ? undefined : "image/*"}
            />
          </>
        )}

        <Tooltip title={canFire ? "Send to both A and B" : "Pick both versions and type a prompt"}>
          <span>
            <Fab
              size="medium"
              onClick={handleSend}
              disabled={!canFire}
              sx={{
                flexShrink: 0,
                color: "#fff",
                background: canFire
                  ? "linear-gradient(135deg, #0e7490 0%, #7c3aed 100%)"
                  : "rgba(15,23,42,0.15)",
                boxShadow: canFire
                  ? "0 6px 16px rgba(124,58,237,0.25), 0 2px 4px rgba(14,116,144,0.2)"
                  : "none",
                "&:hover": {
                  background: canFire
                    ? "linear-gradient(135deg, #155e75 0%, #6d28d9 100%)"
                    : undefined,
                  transform: canFire ? "translateY(-1px)" : undefined,
                  boxShadow: canFire
                    ? "0 10px 24px rgba(124,58,237,0.3), 0 3px 6px rgba(14,116,144,0.25)"
                    : "none",
                },
                transition: "transform 0.15s ease, box-shadow 0.15s ease",
              }}
            >
              <Send fontSize="small" />
            </Fab>
          </span>
        </Tooltip>
      </Box>
    </Box>
  );
}
