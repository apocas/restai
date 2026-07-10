import { useState, useRef, useEffect } from "react";
import { Box, Chip, MenuItem, TextField, Tooltip, Typography } from "@mui/material";
import { Send, CloudUpload, DeleteSweep, Mic, ExpandMore, ChevronRight } from "@mui/icons-material";
import { toast } from "react-toastify";
import { AudioRecorder } from "react-audio-voice-recorder";
import ReactJson from "@microlink/react-json-view";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FONT_MONO } from "app/components/page/pageStyles";
import {
  PlaygroundTile, HeaderBar, Eyebrow, Stream, Composer,
  PulseDot, PrimaryAction, GhostAction, fieldSx, HAIRLINE,
} from "./generatorKit";

const ACCENT = "#d97706";        // amber-600 — audio / waveform
const ACCENT_SOFT = "rgba(217,119,6,0.10)";

// A static waveform ribbon — the sound motif. Heights derive from the index
// so it's stable across renders (no Math.random churn).
function Waveform({ bars = 40, height = 34, opacity = 1 }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: "3px", height, opacity }}>
      {Array.from({ length: bars }).map((_, i) => {
        const h = 6 + ((i * 37) % 100) / 100 * (height - 6);
        return <Box key={i} sx={{ width: 3, height: h, borderRadius: 2, background: ACCENT, opacity: 0.35 + ((i * 53) % 60) / 100 }} />;
      })}
    </Box>
  );
}

function AudioMessage({ message }) {
  const [showRaw, setShowRaw] = useState(false);
  const answer = message.answer;

  return (
    <Box sx={{ mb: 3.5 }}>
      {/* Source — the submitted clip. */}
      <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1.25 }}>
        <Box sx={{ maxWidth: "80%", textAlign: "right" }}>
          <Eyebrow accent={ACCENT} sx={{ display: "block", mb: 0.5 }}>Source</Eyebrow>
          <Box sx={{
            display: "inline-block", textAlign: "left", padding: "10px 14px",
            borderRadius: "14px 14px 4px 14px", background: ACCENT_SOFT, border: `1px solid ${ACCENT}22`,
          }}>
            {message.prompt && message.prompt !== "(audio)" && (
              <Typography variant="body2" sx={{ color: "#0f172a", whiteSpace: "pre-wrap", mb: 0.75 }}>
                {message.prompt}
              </Typography>
            )}
            {message._audioFile && (
              <Box component="audio" src={URL.createObjectURL(message._audioFile)} controls
                sx={{ maxWidth: 280, height: 34, display: "block" }} />
            )}
            {message._generator && <Eyebrow muted sx={{ display: "block", mt: 0.75 }}>{message._generator}</Eyebrow>}
          </Box>
        </Box>
      </Box>

      {/* Readout — the transcript. */}
      <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
        <Box sx={{ maxWidth: "84%", width: answer ? "84%" : "auto" }}>
          <Eyebrow accent={ACCENT} sx={{ display: "block", mb: 0.5 }}>Transcript</Eyebrow>
          {answer ? (
            <Box sx={{ padding: "12px 16px", borderRadius: 2, border: `1px solid ${HAIRLINE}`, background: "#fff" }}>
              {answer.text
                ? <Typography variant="body2" sx={{ color: "#0f172a", whiteSpace: "pre-wrap", lineHeight: 1.7 }}>{answer.text}</Typography>
                : <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>No text returned.</Typography>}

              {/* Raw·JSON disclosure — collapsed by default so the transcript reads clean. */}
              <Box
                component="button"
                onClick={() => setShowRaw((v) => !v)}
                aria-expanded={showRaw}
                sx={{
                  display: "inline-flex", alignItems: "center", gap: 0.5, mt: 1.25, cursor: "pointer",
                  border: "none", background: "none", padding: 0, font: "inherit",
                  color: "rgba(15,23,42,0.5)", "&:hover": { color: ACCENT },
                  "&:focus-visible": { outline: `2px solid ${ACCENT}`, outlineOffset: 2, borderRadius: 2 },
                }}
              >
                {showRaw ? <ExpandMore sx={{ fontSize: 16 }} /> : <ChevronRight sx={{ fontSize: 16 }} />}
                <Eyebrow accent={showRaw ? ACCENT : undefined} muted={!showRaw}>Raw·JSON</Eyebrow>
              </Box>
              {showRaw && (
                <Box sx={{ mt: 0.75, borderRadius: 1, border: `1px solid ${HAIRLINE}`, overflow: "hidden" }}>
                  <ReactJson src={answer} name={false} collapsed={1} enableClipboard
                    displayDataTypes={false} displayObjectSize={false}
                    style={{ fontSize: "0.8em", padding: 10, fontFamily: FONT_MONO }} />
                </Box>
              )}
            </Box>
          ) : (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, padding: "10px 14px", borderRadius: 2, border: `1px dashed ${ACCENT}66`, background: ACCENT_SOFT }}>
              <Waveform bars={18} height={22} />
              <Eyebrow accent={ACCENT}>Transcribing…</Eyebrow>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}

function EmptyReadout() {
  return (
    <Box sx={{ textAlign: "center", mt: 7, color: "rgba(15,23,42,0.55)" }}>
      <Box sx={{ display: "flex", justifyContent: "center", mb: 2.5 }}>
        <Waveform bars={48} height={46} />
      </Box>
      <Eyebrow accent={ACCENT} sx={{ display: "block", mb: 1 }}>Nothing on the wire</Eyebrow>
      <Typography variant="body2" sx={{ maxWidth: 400, mx: "auto" }}>
        Record a clip or upload an audio file, then send it to transcribe. Set a
        language code (e.g. <b>en</b>, <b>pt</b>) for better accuracy.
      </Typography>
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
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const handleSend = async () => {
    if (!audioFile) { toast.error("Record or upload an audio clip first"); return; }
    if (!generator) { toast.error("Select an engine first"); return; }

    const prompt = inputText.trim();
    setIsLoading(true);
    setInputText("");
    setMessages((prev) => [...prev, { prompt: prompt || "(audio)", _generator: generator, _audioFile: audioFile, answer: null }]);

    const formData = new FormData();
    formData.append("file", audioFile);
    formData.append("prompt", prompt);
    formData.append("language", language);

    try {
      const response = await api.post(`/audio/${generator}/transcript`, formData, auth.user.token);
      setMessages((prev) => {
        const u = [...prev];
        u[u.length - 1] = { ...u[u.length - 1], answer: response, prompt: prompt || "(audio)" };
        return u;
      });
    } catch (e) {
      setMessages((prev) => {
        const u = [...prev];
        u[u.length - 1] = { ...u[u.length - 1], answer: { text: "Transcription failed. Check the engine and try again." } };
        return u;
      });
    } finally {
      setIsLoading(false);
      setAudioFile(null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (file) setAudioFile(file);
    e.target.value = "";
  };

  return (
    <PlaygroundTile accent={ACCENT}>
      <HeaderBar>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, minWidth: 0 }}>
          <PulseDot accent={ACCENT} active={isLoading} />
          <Eyebrow accent={ACCENT}>Audio Transcription</Eyebrow>
          <Eyebrow muted>· {String(messages.length).padStart(2, "0")} take{messages.length === 1 ? "" : "s"}</Eyebrow>
        </Box>
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <TextField select size="small" label="Engine" value={generator}
            onChange={(e) => setGenerator(e.target.value)} sx={{ minWidth: 170, ...fieldSx(ACCENT) }}>
            {generators.length === 0 && <MenuItem disabled value="">No engines configured</MenuItem>}
            {generators.map((g) => <MenuItem key={g} value={g}>{g}</MenuItem>)}
          </TextField>
          <TextField size="small" label="Language" value={language}
            onChange={(e) => setLanguage(e.target.value)} placeholder="en"
            sx={{ width: 110, ...fieldSx(ACCENT) }} />
        </Box>
      </HeaderBar>

      <Stream ref={scrollRef}>
        {messages.length === 0
          ? <EmptyReadout />
          : messages.map((msg, i) => <AudioMessage key={i} message={msg} />)}
      </Stream>

      {audioFile && (
        <Box sx={{ px: 1.75, pt: 1.25, display: "flex" }}>
          <Chip label={audioFile.name || "Recording ready"} onDelete={() => setAudioFile(null)} size="small"
            sx={{ borderColor: `${ACCENT}55`, color: ACCENT, background: ACCENT_SOFT }} variant="outlined" />
        </Box>
      )}

      <Composer>
        <TextField
          fullWidth size="small" placeholder="Optional prompt or context…"
          value={inputText} onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown} multiline maxRows={3} disabled={isLoading}
          sx={fieldSx(ACCENT)}
        />
        {navigator.mediaDevices ? (
          <Box sx={{ display: "inline-flex", alignItems: "center", "& .audio-recorder": { boxShadow: "none" } }}>
            <AudioRecorder
              onRecordingComplete={(blob) => setAudioFile(blob)}
              audioTrackConstraints={{ noiseSuppression: true, echoCancellation: true }}
              onNotAllowedOrFound={(err) => console.warn(err)}
              downloadOnSavePress={false}
              downloadFileExtension="webm"
              mediaRecorderOptions={{ audioBitsPerSecond: 128000 }}
            />
          </Box>
        ) : (
          <Tooltip title="Microphone requires HTTPS">
            <span><GhostAction accent={ACCENT} disabled><Mic sx={{ fontSize: 20 }} /></GhostAction></span>
          </Tooltip>
        )}
        <Tooltip title="Upload audio">
          <label htmlFor="audio-upload" style={{ display: "inline-flex" }}>
            <GhostAction accent={ACCENT} component="span"><CloudUpload sx={{ fontSize: 20 }} /></GhostAction>
          </label>
        </Tooltip>
        <input onChange={handleFileSelect} id="audio-upload" type="file" accept="audio/*" style={{ display: "none" }} />
        <Tooltip title="Clear stream">
          <GhostAction accent={ACCENT} onClick={() => { setMessages([]); setAudioFile(null); }}>
            <DeleteSweep sx={{ fontSize: 20 }} />
          </GhostAction>
        </Tooltip>
        <Tooltip title="Transcribe">
          <span>
            <PrimaryAction accent={ACCENT} onClick={handleSend} disabled={isLoading || !audioFile}>
              <Send sx={{ fontSize: 20 }} />
            </PrimaryAction>
          </span>
        </Tooltip>
      </Composer>
    </PlaygroundTile>
  );
}
