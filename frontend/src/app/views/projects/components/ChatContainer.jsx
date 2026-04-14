import { useState } from "react";
import {
  Box, Card, Chip, Collapse, Divider, FormControlLabel, IconButton, Switch, Tab, Tabs, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { Chat, Compare, DataObject } from "@mui/icons-material";
import ChatPanel from "./ChatPanel";
import CompareMode from "./CompareMode";

const ChatRoot = styled(Card)({
  height: "100%",
  display: "flex",
  flexDirection: "column",
});

export default function ChatContainer({ project }) {
  const [mode, setMode] = useState(0); // 0 = chat, 1 = compare
  const [chatMode, setChatMode] = useState(true);
  const [streaming, setStreaming] = useState(true);
  const [showContext, setShowContext] = useState(false);
  const [contextText, setContextText] = useState("{}");
  const [contextError, setContextError] = useState(false);

  const handleContextChange = (e) => {
    const val = e.target.value;
    setContextText(val);
    try {
      JSON.parse(val);
      setContextError(false);
    } catch {
      setContextError(true);
    }
  };

  const parsedContext = (() => {
    try {
      const obj = JSON.parse(contextText);
      if (obj && typeof obj === "object" && !Array.isArray(obj) && Object.keys(obj).length > 0) return obj;
    } catch {}
    return null;
  })();

  return (
    <ChatRoot elevation={3}>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", px: 2, py: 1, flexWrap: "wrap", gap: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Typography variant="subtitle1" fontWeight="bold">
            {project.human_name || project.name}
          </Typography>
          {project.llm && (
            <Chip label={project.llm} size="small" variant="outlined" />
          )}
          <Chip label={project.type} size="small" color="primary" variant="outlined" />
        </Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          {mode === 0 && (
            <>
              <FormControlLabel
                control={<Switch size="small" checked={chatMode} onChange={(e) => setChatMode(e.target.checked)} />}
                label={<Typography variant="caption">{chatMode ? "Chat" : "QA"}</Typography>}
              />
              <FormControlLabel
                control={<Switch size="small" checked={streaming} onChange={(e) => setStreaming(e.target.checked)} />}
                label={<Typography variant="caption">Stream</Typography>}
              />
              <Tooltip title="Inject context variables into the system prompt">
                <IconButton
                  size="small"
                  onClick={() => setShowContext(!showContext)}
                  color={parsedContext ? "primary" : "default"}
                >
                  <DataObject fontSize="small" />
                </IconButton>
              </Tooltip>
            </>
          )}
          <Tabs
            value={mode}
            onChange={(_, v) => setMode(v)}
            sx={{ minHeight: 36, "& .MuiTab-root": { minHeight: 36, py: 0 } }}
          >
            <Tab icon={<Chat fontSize="small" />} iconPosition="start" label="Chat" />
            <Tab icon={<Compare fontSize="small" />} iconPosition="start" label="Compare" />
          </Tabs>
        </Box>
      </Box>

      <Collapse in={showContext}>
        <Box sx={{ px: 2, py: 1.5, bgcolor: "action.hover" }}>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
            Context JSON — injected as <code>{"{{context.key}}"}</code> placeholders in the system prompt
          </Typography>
          <TextField
            fullWidth
            size="small"
            multiline
            rows={3}
            value={contextText}
            onChange={handleContextChange}
            error={contextError}
            helperText={contextError ? "Invalid JSON" : undefined}
            placeholder='{"user_name": "John", "plan": "pro"}'
            InputProps={{ sx: { fontFamily: "monospace", fontSize: "0.82rem" } }}
          />
        </Box>
      </Collapse>

      <Divider />

      {/* Body */}
      <Box sx={{ flex: 1, minHeight: 0, p: mode === 1 ? 2 : 0 }}>
        {mode === 0 && (
          <ChatPanel project={project} chatMode={chatMode} streaming={streaming} context={parsedContext} />
        )}
        {mode === 1 && (
          <CompareMode project={project} />
        )}
      </Box>
    </ChatRoot>
  );
}
