import { useState, useRef, useEffect } from "react";
import { Box, Chip, MenuItem, TextField, Tooltip, Typography } from "@mui/material";
import { Send, CloudUpload, DeleteSweep, Download } from "@mui/icons-material";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import {
  PlaygroundTile, HeaderBar, Eyebrow, Stream, Composer,
  PulseDot, PrimaryAction, GhostAction, fieldSx, HAIRLINE,
} from "./generatorKit";

const ACCENT = "#7c3aed";        // violet-600 — image synthesis
const ACCENT_SOFT = "rgba(124,58,237,0.10)";

// Four corner registration marks — the darkroom/contact-plate motif that
// tells the eye "this is a captured exposure", not a chat bubble.
function RegTicks() {
  const base = { position: "absolute", width: 10, height: 10, borderColor: ACCENT, borderStyle: "solid", borderWidth: 0 };
  return (
    <>
      <Box sx={{ ...base, top: 4, left: 4, borderTopWidth: 2, borderLeftWidth: 2 }} />
      <Box sx={{ ...base, top: 4, right: 4, borderTopWidth: 2, borderRightWidth: 2 }} />
      <Box sx={{ ...base, bottom: 4, left: 4, borderBottomWidth: 2, borderLeftWidth: 2 }} />
      <Box sx={{ ...base, bottom: 4, right: 4, borderBottomWidth: 2, borderRightWidth: 2 }} />
    </>
  );
}

function ImageMessage({ message, index }) {
  const plateNo = String(index + 1).padStart(2, "0");
  const openFull = () => {
    const w = window.open();
    if (w) w.document.write(`<title>Plate ${plateNo}</title><body style="margin:0;background:#0f172a"><img src="data:image/png;base64,${message.image}" style="max-width:100%;display:block;margin:auto" /></body>`);
  };

  return (
    <Box sx={{ mb: 3.5 }}>
      {/* Brief — the prompt, framed as a right-aligned request slip. */}
      {message.prompt && (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1.25 }}>
          <Box sx={{ maxWidth: "78%", textAlign: "right" }}>
            <Eyebrow accent={ACCENT} sx={{ display: "block", mb: 0.5 }}>Brief</Eyebrow>
            <Box sx={{
              display: "inline-block", textAlign: "left", padding: "10px 14px",
              borderRadius: "14px 14px 4px 14px", background: ACCENT_SOFT,
              border: `1px solid ${ACCENT}22`,
            }}>
              {message._inputImage && (
                <Box component="img" src={message._inputImage}
                  sx={{ maxWidth: "100%", maxHeight: 160, borderRadius: 1, mb: 1, display: "block" }} />
              )}
              <Typography variant="body2" sx={{ color: "#0f172a", whiteSpace: "pre-wrap" }}>
                {message.prompt}
              </Typography>
            </Box>
          </Box>
        </Box>
      )}

      {/* Plate — the exposure. */}
      <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
        <Box sx={{ maxWidth: "82%" }}>
          {message.image ? (
            <Box>
              <Box sx={{
                position: "relative", padding: "14px", background: "#fff",
                border: `1px solid ${HAIRLINE}`, borderRadius: 2,
                boxShadow: "0 8px 24px rgba(15,23,42,0.08)",
              }}>
                <RegTicks />
                <Box component="img" src={`data:image/png;base64,${message.image}`}
                  onClick={openFull}
                  sx={{ maxWidth: "100%", maxHeight: 460, display: "block", cursor: "zoom-in", borderRadius: 0.5 }} />
              </Box>
              {/* Caption strip — plate index + generator + save. */}
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 0.75, pl: 0.25 }}>
                <Eyebrow accent={ACCENT}>Plate·{plateNo}</Eyebrow>
                {message._generator && <Eyebrow muted>· {message._generator}</Eyebrow>}
                <Box sx={{ flex: 1 }} />
                <Tooltip title="Save image">
                  <Box component="a" download={`plate-${plateNo}.png`}
                    href={`data:image/png;base64,${message.image}`}
                    sx={{ display: "inline-flex", color: "rgba(15,23,42,0.5)", "&:hover": { color: ACCENT } }}>
                    <Download sx={{ fontSize: 18 }} />
                  </Box>
                </Tooltip>
              </Box>
            </Box>
          ) : message.answer ? (
            <Box sx={{ padding: "10px 14px", borderRadius: 2, border: `1px solid ${HAIRLINE}`, background: "#fff" }}>
              <Eyebrow sx={{ display: "block", mb: 0.5 }} accent="#dc2626">Failed</Eyebrow>
              <Typography variant="body2" color="error">{message.answer}</Typography>
            </Box>
          ) : (
            // Developing — a blank plate under exposure.
            <Box sx={{
              position: "relative", width: 260, height: 200, background: ACCENT_SOFT,
              border: `1px dashed ${ACCENT}66`, borderRadius: 2,
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <RegTicks />
              <Eyebrow accent={ACCENT}>Exposing…</Eyebrow>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}

// Aperture crosshair — the empty-state motif.
function EmptyPlate() {
  return (
    <Box sx={{ textAlign: "center", mt: 7, color: "rgba(15,23,42,0.55)" }}>
      <Box sx={{
        width: 92, height: 92, margin: "0 auto 20px", borderRadius: "50%",
        border: `1px solid ${ACCENT}55`, position: "relative",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}>
        <Box sx={{ position: "absolute", width: "100%", height: 1, background: `${ACCENT}44` }} />
        <Box sx={{ position: "absolute", height: "100%", width: 1, background: `${ACCENT}44` }} />
        <Box sx={{ width: 34, height: 34, borderRadius: "50%", border: `2px solid ${ACCENT}`, background: ACCENT_SOFT }} />
      </Box>
      <Eyebrow accent={ACCENT} sx={{ display: "block", mb: 1 }}>No exposures yet</Eyebrow>
      <Typography variant="body2" sx={{ maxWidth: 380, mx: "auto" }}>
        Pick a generator and describe the image you want. Attach a reference to
        guide an image-to-image pass.
      </Typography>
    </Box>
  );
}

export default function ImageChatContainer({ generators }) {
  const auth = useAuth();
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [image, setImage] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [generator, setGenerator] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages]);

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text && !image) return;
    if (!generator) { toast.error("Select a generator first"); return; }

    setIsLoading(true);
    setInputText("");
    setMessages((prev) => [...prev, { prompt: text, _generator: generator, _inputImage: image, image: null, answer: null }]);

    const body = { prompt: text };
    if (image) body.image = image.includes("base64,") ? image.split(",")[1] : image;

    try {
      const response = await api.post(`/image/${generator}/generate`, body, auth.user.token);
      setMessages((prev) => {
        const u = [...prev];
        u[u.length - 1] = { ...u[u.length - 1], ...response, prompt: response.prompt || text };
        return u;
      });
    } catch (e) {
      setMessages((prev) => {
        const u = [...prev];
        u[u.length - 1] = { ...u[u.length - 1], answer: "Generation failed. Check the generator credentials and try again." };
        return u;
      });
    } finally {
      setIsLoading(false);
      setImage(null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result);
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  return (
    <PlaygroundTile accent={ACCENT}>
      <HeaderBar>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.25, minWidth: 0 }}>
          <PulseDot accent={ACCENT} active={isLoading} />
          <Eyebrow accent={ACCENT}>Image Synthesis</Eyebrow>
          <Eyebrow muted>· {String(messages.length).padStart(2, "0")} plate{messages.length === 1 ? "" : "s"}</Eyebrow>
        </Box>
        <TextField
          select size="small" label="Generator" value={generator}
          onChange={(e) => setGenerator(e.target.value)}
          sx={{ minWidth: 200, ...fieldSx(ACCENT) }}
        >
          {generators.length === 0 && <MenuItem disabled value="">No generators configured</MenuItem>}
          {generators.map((g) => <MenuItem key={g} value={g}>{g}</MenuItem>)}
        </TextField>
      </HeaderBar>

      <Stream ref={scrollRef}>
        {messages.length === 0
          ? <EmptyPlate />
          : messages.map((msg, i) => <ImageMessage key={i} message={msg} index={i} />)}
      </Stream>

      {image && (
        <Box sx={{ px: 1.75, pt: 1.25, display: "flex" }}>
          <Chip label="Reference attached" onDelete={() => setImage(null)} size="small"
            sx={{ borderColor: `${ACCENT}55`, color: ACCENT, background: ACCENT_SOFT }} variant="outlined" />
        </Box>
      )}

      <Composer>
        <TextField
          fullWidth size="small" placeholder="Describe the image…"
          value={inputText} onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown} multiline maxRows={4} disabled={isLoading}
          sx={fieldSx(ACCENT)}
        />
        <Tooltip title="Attach reference">
          <label htmlFor="image-gen-upload" style={{ display: "inline-flex" }}>
            <GhostAction accent={ACCENT} component="span"><CloudUpload sx={{ fontSize: 20 }} /></GhostAction>
          </label>
        </Tooltip>
        <input onChange={handleFileSelect} id="image-gen-upload" type="file" accept="image/*" style={{ display: "none" }} />
        <Tooltip title="Clear stream">
          <GhostAction accent={ACCENT} onClick={() => { setMessages([]); setImage(null); }}>
            <DeleteSweep sx={{ fontSize: 20 }} />
          </GhostAction>
        </Tooltip>
        <Tooltip title="Generate">
          <span>
            <PrimaryAction accent={ACCENT} onClick={handleSend} disabled={isLoading || (!inputText.trim() && !image)}>
              <Send sx={{ fontSize: 20 }} />
            </PrimaryAction>
          </span>
        </Tooltip>
      </Composer>
    </PlaygroundTile>
  );
}
