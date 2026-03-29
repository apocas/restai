import { useState, useEffect } from "react";
import {
  Box, Card, Divider, Fab, Grid, MenuItem, TextField, Typography, styled,
} from "@mui/material";
import { Send, CloudUpload } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import ChatPanel from "./ChatPanel";

const HiddenInput = styled("input")({ display: "none" });

export default function CompareMode({ project }) {
  const auth = useAuth();
  const [versions, setVersions] = useState([]);
  const [selectedA, setSelectedA] = useState("");
  const [selectedB, setSelectedB] = useState("");
  const [sharedInput, setSharedInput] = useState("");
  const [sharedImage, setSharedImage] = useState(null);
  const [questionA, setQuestionA] = useState(null);
  const [questionB, setQuestionB] = useState(null);
  const [counter, setCounter] = useState(0);

  useEffect(() => {
    api.get(`/projects/${project.id}/prompts`, auth.user.token, { silent: true })
      .then((data) => {
        setVersions(data || []);
        const active = (data || []).find(v => v.is_active);
        if (active) {
          setSelectedA(active.id);
          // Default B to the previous version if available
          const prev = (data || []).find(v => !v.is_active);
          if (prev) setSelectedB(prev.id);
        }
      })
      .catch(() => {});
  }, [project.id]);

  const getSystemPrompt = (versionId) => {
    const v = versions.find(x => x.id === versionId);
    return v ? v.system_prompt : null;
  };

  const getVersionLabel = (versionId) => {
    const v = versions.find(x => x.id === versionId);
    if (!v) return "";
    return `v${v.version}${v.is_active ? " (active)" : ""}`;
  };

  const handleSend = () => {
    const text = sharedInput.trim();
    if (!text && !sharedImage) return;
    const c = counter + 1;
    setCounter(c);
    setQuestionA({ text, image: sharedImage, ts: c });
    setQuestionB({ text, image: sharedImage, ts: c });
    setSharedInput("");
    setSharedImage(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setSharedImage(reader.result);
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  if (versions.length < 1) {
    return (
      <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
        <Typography variant="h6">No prompt versions available</Typography>
        <Typography variant="body2">
          Edit the project's system message and save it to create prompt versions for comparison.
        </Typography>
      </Box>
    );
  }

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Version selectors */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6}>
          <TextField
            select fullWidth size="small" label="Version A"
            value={selectedA}
            onChange={(e) => setSelectedA(e.target.value)}
          >
            {versions.map(v => (
              <MenuItem key={v.id} value={v.id}>
                v{v.version}{v.is_active ? " (active)" : ""} — {v.system_prompt ? v.system_prompt.substring(0, 60) + "..." : "(empty)"}
              </MenuItem>
            ))}
          </TextField>
        </Grid>
        <Grid item xs={6}>
          <TextField
            select fullWidth size="small" label="Version B"
            value={selectedB}
            onChange={(e) => setSelectedB(e.target.value)}
          >
            {versions.map(v => (
              <MenuItem key={v.id} value={v.id}>
                v{v.version}{v.is_active ? " (active)" : ""} — {v.system_prompt ? v.system_prompt.substring(0, 60) + "..." : "(empty)"}
              </MenuItem>
            ))}
          </TextField>
        </Grid>
      </Grid>

      {/* Side-by-side panels */}
      <Grid container spacing={2} sx={{ flex: 1, minHeight: 0 }}>
        <Grid item xs={6}>
          <Card elevation={2} sx={{ height: "100%" }}>
            <Box sx={{ px: 2, py: 1, backgroundColor: "action.hover" }}>
              <Typography variant="caption" fontWeight="bold" color="primary">
                {getVersionLabel(selectedA) || "Select Version A"}
              </Typography>
            </Box>
            <Divider />
            <ChatPanel
              project={project}
              systemOverride={getSystemPrompt(selectedA)}
              sharedQuestion={questionA}
              compact
            />
          </Card>
        </Grid>
        <Grid item xs={6}>
          <Card elevation={2} sx={{ height: "100%" }}>
            <Box sx={{ px: 2, py: 1, backgroundColor: "action.hover" }}>
              <Typography variant="caption" fontWeight="bold" color="secondary">
                {getVersionLabel(selectedB) || "Select Version B"}
              </Typography>
            </Box>
            <Divider />
            <ChatPanel
              project={project}
              systemOverride={getSystemPrompt(selectedB)}
              sharedQuestion={questionB}
              compact
            />
          </Card>
        </Grid>
      </Grid>

      {/* Shared input */}
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1, pt: 2, borderTop: 1, borderColor: "divider", mt: 2 }}>
        <TextField
          fullWidth size="small"
          placeholder="Send the same question to both versions..."
          value={sharedInput}
          onChange={(e) => setSharedInput(e.target.value)}
          onKeyDown={handleKeyDown}
          multiline maxRows={3}
        />
        {(project.type === "inference" || project.type === "block") && (
          <>
            <label htmlFor="compare-upload">
              <Fab color="default" size="small" component="span">
                <CloudUpload fontSize="small" />
              </Fab>
            </label>
            <HiddenInput onChange={handleFileSelect} id="compare-upload" type="file" accept="image/*" />
          </>
        )}
        <Fab color="primary" size="small" onClick={handleSend} disabled={!selectedA || !selectedB}>
          <Send fontSize="small" />
        </Fab>
      </Box>
    </Box>
  );
}
