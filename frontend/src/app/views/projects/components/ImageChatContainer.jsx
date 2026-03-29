import { useState, useRef, useEffect } from "react";
import {
  Box, Card, Chip, Divider, Fab, MenuItem, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { Send, CloudUpload, DeleteSweep, Brush } from "@mui/icons-material";
import { toast } from "react-toastify";
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

function ImageMessage({ message }) {
  return (
    <Box sx={{ mb: 2 }}>
      {/* Prompt */}
      {message.prompt && (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <PromptBubble>
            {message._inputImage && (
              <Box
                component="img"
                src={message._inputImage}
                sx={{ maxWidth: "100%", maxHeight: 200, borderRadius: 1, mb: 1, display: "block" }}
              />
            )}
            <Typography variant="body2">{message.prompt}</Typography>
            {message._generator && (
              <Chip label={message._generator} size="small" sx={{ mt: 0.5, backgroundColor: "rgba(255,255,255,0.2)", color: "#fff" }} />
            )}
          </PromptBubble>
        </Box>
      )}

      {/* Result */}
      <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
        <ResultBubble>
          {message.image ? (
            <Box
              component="img"
              src={`data:image/png;base64,${message.image}`}
              sx={{ maxWidth: "100%", maxHeight: 500, borderRadius: 1, display: "block", cursor: "pointer" }}
              onClick={() => {
                const w = window.open();
                w.document.write(`<img src="data:image/png;base64,${message.image}" />`);
              }}
            />
          ) : message.answer ? (
            <Typography variant="body2" color="error">{message.answer}</Typography>
          ) : (
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
              Generating...
            </Typography>
          )}
        </ResultBubble>
      </Box>
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
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    const text = inputText.trim();
    if (!text && !image) return;
    if (!generator) {
      toast.error("Please select a generator");
      return;
    }

    setIsLoading(true);
    setInputText("");

    const msg = { prompt: text, _generator: generator, _inputImage: image, image: null, answer: null };
    setMessages(prev => [...prev, msg]);

    const body = { prompt: text };
    if (image) {
      body.image = image.includes("base64,") ? image.split(",")[1] : image;
    }

    try {
      const response = await api.post(`/image/${generator}/generate`, body, auth.user.token);
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          ...response,
          prompt: response.prompt || text,
        };
        return updated;
      });
    } catch (e) {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          ...updated[updated.length - 1],
          answer: "Error: generation failed.",
        };
        return updated;
      });
    } finally {
      setIsLoading(false);
      setImage(null);
    }
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
    reader.onload = () => setImage(reader.result);
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  const handleClear = () => {
    setMessages([]);
    setImage(null);
  };

  return (
    <Card elevation={3} sx={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Header */}
      <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", px: 2, py: 1 }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Brush />
          <Typography variant="subtitle1" fontWeight="bold">Image Generation</Typography>
        </Box>
        <TextField
          select
          size="small"
          label="Generator"
          value={generator}
          onChange={(e) => setGenerator(e.target.value)}
          sx={{ minWidth: 200 }}
        >
          {generators.map((g) => (
            <MenuItem key={g} value={g}>{g}</MenuItem>
          ))}
        </TextField>
      </Box>

      <Divider />

      {/* Messages */}
      <Box sx={{ flex: 1, overflow: "auto", minHeight: 400 }} ref={scrollRef}>
        <Box sx={{ p: 2 }}>
          {messages.length === 0 && (
            <Box sx={{ textAlign: "center", mt: 8, color: "text.secondary" }}>
              <Brush sx={{ fontSize: 48, mb: 1, opacity: 0.3 }} />
              <Typography variant="body2">
                Select a generator and describe the image you want to create.
              </Typography>
              <Typography variant="caption" color="text.secondary">
                You can also upload a reference image for image-to-image generation.
              </Typography>
            </Box>
          )}
          {messages.map((msg, i) => (
            <ImageMessage key={i} message={msg} />
          ))}
        </Box>
      </Box>

      {/* Image preview */}
      {image && (
        <Box sx={{ px: 2, pb: 1 }}>
          <Chip
            label="Reference image attached"
            onDelete={() => setImage(null)}
            size="small"
            color="primary"
            variant="outlined"
          />
        </Box>
      )}

      {/* Input */}
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1, p: 2, borderTop: 1, borderColor: "divider" }}>
        <TextField
          fullWidth
          size="small"
          placeholder="Describe the image..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          multiline
          maxRows={4}
          disabled={isLoading}
        />
        <label htmlFor="image-gen-upload">
          <Fab color="default" size="small" component="span">
            <CloudUpload fontSize="small" />
          </Fab>
        </label>
        <HiddenInput onChange={handleFileSelect} id="image-gen-upload" type="file" accept="image/*" />
        <Tooltip title="Clear">
          <Fab color="default" size="small" onClick={handleClear}>
            <DeleteSweep fontSize="small" />
          </Fab>
        </Tooltip>
        <Fab color="primary" size="small" onClick={handleSend} disabled={isLoading}>
          <Send fontSize="small" />
        </Fab>
      </Box>
    </Card>
  );
}
