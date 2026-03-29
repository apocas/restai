import { useState, useRef, useEffect } from "react";
import {
  Accordion, AccordionDetails, AccordionSummary, Box, Card, Chip, Divider,
  Fab, MenuItem, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { Send, CloudUpload, DeleteSweep, Mic, ExpandMore } from "@mui/icons-material";
import { toast } from "react-toastify";
import { AudioRecorder } from "react-audio-voice-recorder";
import ReactJson from "@microlink/react-json-view";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const HiddenInput = styled("input")({ display: "none" });

const PromptBubble = styled(Box)(({ theme }) => ({
  backgroundColor: theme.palette.primary.main,
  color: "#fff",
  padding: "10px 16px",
  borderRadius: "16px 16px 4px 16px",
  maxWidth: "80%",
  marginLeft: "auto",
  wordBreak: "break-word",
  whiteSpace: "pre-wrap",
}));

const ResultBubble = styled(Box)(({ theme }) => ({
  backgroundColor: theme.palette.mode === "dark" ? "#2d2d2d" : "#f5f5f5",
  padding: "10px 16px",
  borderRadius: "16px 16px 16px 4px",
  maxWidth: "80%",
  wordBreak: "break-word",
}));

function AudioMessage({ message }) {
  return (
    <Box sx={{ mb: 2 }}>
      {/* Prompt */}
      <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
        <PromptBubble>
          {message.prompt && (
            <Typography variant="body2">{message.prompt}</Typography>
          )}
          {message._generator && (
            <Chip label={message._generator} size="small" sx={{ mt: 0.5, backgroundColor: "rgba(255,255,255,0.2)", color: "#fff" }} />
          )}
          {message._audioFile && (
            <Box sx={{ mt: 1 }}>
              <audio src={URL.createObjectURL(message._audioFile)} controls style={{ maxWidth: "100%" }} />
            </Box>
          )}
        </PromptBubble>
      </Box>

      {/* Result */}
      <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
        <ResultBubble>
          {message.answer ? (
            <>
              {/* Main transcription text */}
              {message.answer.text && (
                <Typography variant="body2" sx={{ mb: 1, whiteSpace: "pre-wrap" }}>
                  {message.answer.text}
                </Typography>
              )}
              {/* Full response details — collapsible read-only JSON */}
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1, mb: 0.5 }}>Output</Typography>
              <ReactJson
                src={message.answer}
                name={false}
                collapsed={2}
                enableClipboard
                displayDataTypes={false}
                displayObjectSize={false}
                style={{ fontSize: "0.85em", borderRadius: 4, padding: 8 }}
              />
            </>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
              Transcribing...
            </Typography>
          )}
        </ResultBubble>
      </Box>
    </Box>
  );
}

export default function AudioChatContainer({ generators }) {
  const auth = useAuth();
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [audioFile, setAudioFile] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [generator, setGenerator] = useState("");
  const [language, setLanguage] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    if (!audioFile) {
      toast.error("Please record or upload an audio file");
      return;
    }
    if (!generator) {
      toast.error("Please select a generator");
      return;
    }

    const prompt = inputText.trim();
    setIsLoading(true);
    setInputText("");

    const msg = { prompt: prompt || "(audio)", _generator: generator, _audioFile: audioFile, answer: null };
    setMessages(prev => [...prev, msg]);

    const formData = new FormData();
    formData.append("file", audioFile);
    formData.append("prompt", prompt);
    formData.append("language", language);

    try {
      const response = await api.post(`/audio/${generator}/transcript`, formData, auth.user.token);
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          answer: response,
          prompt: prompt || "(audio)",
        };
        return updated;
      });
    } catch (e) {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          answer: { text: "Error: transcription failed." },
        };
        return updated;
      });
    } finally {
      setIsLoading(false);
      setAudioFile(null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) setAudioFile(file);
    e.target.value = "";
  };

  const handleRecordingComplete = (blob) => {
    setAudioFile(blob);
  };

  const handleClear = () => {
    setMessages([]);
    setAudioFile(null);
  };

  return (
    <Card elevation={3} sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", px: 2, py: 1, flexWrap: "wrap", gap: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Mic />
          <Typography variant="subtitle1" fontWeight="bold">Audio Transcription</Typography>
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <TextField
            select size="small" label="Generator"
            value={generator}
            onChange={(e) => setGenerator(e.target.value)}
            sx={{ minWidth: 180 }}
          >
            {generators.map((g) => (
              <MenuItem key={g} value={g}>{g}</MenuItem>
            ))}
          </TextField>
          <TextField
            size="small" label="Language"
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            sx={{ width: 120 }}
            placeholder="en"
          />
        </Box>
      </Box>

      <Divider />

      {/* Messages */}
      <Box sx={{ flex: 1, overflow: "auto", minHeight: 400 }} ref={scrollRef}>
        <Box sx={{ p: 2 }}>
          {messages.length === 0 && (
            <Box sx={{ textAlign: "center", mt: 8, color: "text.secondary" }}>
              <Mic sx={{ fontSize: 48, mb: 1, opacity: 0.3 }} />
              <Typography variant="body2">
                Record audio with the microphone or upload an audio file, then hit send.
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Optionally set a language code (e.g. "en", "pt") for better accuracy.
              </Typography>
            </Box>
          )}
          {messages.map((msg, i) => (
            <AudioMessage key={i} message={msg} />
          ))}
        </Box>
      </Box>

      {/* Audio preview */}
      {audioFile && (
        <Box sx={{ px: 2, pb: 1 }}>
          <Chip
            label={audioFile.name || "Recording ready"}
            onDelete={() => setAudioFile(null)}
            size="small"
            color="primary"
            variant="outlined"
          />
        </Box>
      )}

      {/* Input */}
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1, p: 2, borderTop: 1, borderColor: "divider" }}>
        <TextField
          fullWidth size="small"
          placeholder="Optional prompt or context..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          multiline maxRows={3}
          disabled={isLoading}
        />
        {navigator.mediaDevices ? (
          <AudioRecorder
            onRecordingComplete={handleRecordingComplete}
            audioTrackConstraints={{ noiseSuppression: true, echoCancellation: true }}
            onNotAllowedOrFound={(err) => console.warn(err)}
            downloadOnSavePress={false}
            downloadFileExtension="webm"
            mediaRecorderOptions={{ audioBitsPerSecond: 128000 }}
          />
        ) : (
          <Tooltip title="Microphone requires HTTPS">
            <Fab color="default" size="small" disabled>
              <Mic fontSize="small" />
            </Fab>
          </Tooltip>
        )}
        <label htmlFor="audio-upload">
          <Fab color="default" size="small" component="span">
            <CloudUpload fontSize="small" />
          </Fab>
        </label>
        <HiddenInput onChange={handleFileSelect} id="audio-upload" type="file" accept="audio/*" />
        <Tooltip title="Clear">
          <Fab color="default" size="small" onClick={handleClear}>
            <DeleteSweep fontSize="small" />
          </Fab>
        </Tooltip>
        <Fab color="primary" size="small" onClick={handleSend} disabled={isLoading || !audioFile}>
          <Send fontSize="small" />
        </Fab>
      </Box>
    </Card>
  );
}
