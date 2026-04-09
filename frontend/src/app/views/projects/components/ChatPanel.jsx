import { useState, useRef, useEffect, useCallback } from "react";
import {
  Box, Fab, TextField, Tooltip, Typography, Chip, styled,
} from "@mui/material";
import { Send, CloudUpload, DeleteSweep } from "@mui/icons-material";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import MessageBubble from "./MessageBubble";

const HiddenInput = styled("input")({ display: "none" });

const url = process.env.REACT_APP_RESTAI_API_URL || "";

export default function ChatPanel({ project, systemOverride, sharedQuestion, onQuestionSent, chatMode = false, compact = false, streaming = false }) {
  const auth = useAuth();
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [image, setImage] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const scrollRef = useRef(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, streamingText]);

  // Handle shared question from compare mode
  useEffect(() => {
    if (sharedQuestion && sharedQuestion.text) {
      sendMessage(sharedQuestion.text, sharedQuestion.image);
    }
  }, [sharedQuestion]);

  const sendMessageStream = useCallback(async (questionText, img) => {
    const body = { question: questionText, stream: true };
    if (img) body.image = img.includes("base64,") ? img.split(",")[1] : img;
    if (systemOverride) body.system = systemOverride;

    const endpoint = chatMode ? "chat" : "question";
    if (chatMode && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.id) body.id = lastMsg.id;
    }

    setMessages(prev => [...prev, { question: questionText, answer: null, sources: [], _image: img || null }]);
    setStreamingText("");

    let accumulated = "";
    let finalOutput = null;

    await fetchEventSource(url + `/projects/${project.id}/${endpoint}`, {
      method: "POST",
      headers: {
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Authorization": "Basic " + auth.user.token,
      },
      body: JSON.stringify(body),
      onmessage(ev) {
        try {
          const data = JSON.parse(ev.data);
          if (data.answer !== undefined && data.type !== undefined) {
            // Final output with full metadata
            finalOutput = data;
          } else if (data.text !== undefined) {
            accumulated += data.text;
            setStreamingText(accumulated);
          }
        } catch (e) {
          // Non-JSON chunk, ignore
        }
      },
      onclose() {
        setStreamingText("");
        if (finalOutput) {
          setMessages(prev => {
            const updated = [...prev];
            updated[updated.length - 1] = finalOutput;
            return updated;
          });
          if (finalOutput.guard) {
            toast.warning("This question hit the prompt guard.", { position: "top-right" });
          }
          if (project.type === "rag" && finalOutput.sources && finalOutput.sources.length === 0) {
            toast.warning("No sources found. Try decreasing the score cutoff.", { position: "top-right" });
          }
        } else if (accumulated) {
          setMessages(prev => {
            const updated = [...prev];
            const prevId = updated.length > 1 ? updated[updated.length - 2]?.id : undefined;
            updated[updated.length - 1] = { question: questionText, answer: accumulated, sources: [], id: prevId };
            return updated;
          });
        }
        setIsLoading(false);
        setImage(null);
        if (onQuestionSent) onQuestionSent();
      },
      onerror(err) {
        setStreamingText("");
        setMessages(prev => {
          const updated = [...prev];
          const prevId = updated.length > 1 ? updated[updated.length - 2]?.id : undefined;
          updated[updated.length - 1] = { question: questionText, answer: "Error: streaming failed.", sources: [], id: prevId };
          return updated;
        });
        setIsLoading(false);
        setImage(null);
        throw err; // Stop reconnecting
      },
    });
  }, [project.id, auth.user.token, systemOverride, chatMode, messages, onQuestionSent]);

  const sendMessage = useCallback(async (text, img) => {
    if (isLoading) return;
    if (!text && !img) return;

    const questionText = text || "";
    setIsLoading(true);
    setInputText("");

    if (streaming) {
      try {
        await sendMessageStream(questionText, img);
      } catch (e) {
        setIsLoading(false);
        setImage(null);
      }
      return;
    }

    // Non-streaming path
    setMessages(prev => [...prev, { question: questionText, answer: null, sources: [], _image: img || null }]);

    const body = { question: questionText };
    if (img) body.image = img.includes("base64,") ? img.split(",")[1] : img;
    if (systemOverride) body.system = systemOverride;

    const endpoint = chatMode ? "chat" : "question";
    if (chatMode && messages.length > 0) {
      const lastMsg = messages[messages.length - 1];
      if (lastMsg.id) body.id = lastMsg.id;
    }

    try {
      const response = await api.post(
        `/projects/${project.id}/${endpoint}`,
        body,
        auth.user.token
      );
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { ...response, _image: updated[updated.length - 1]._image };
        return updated;
      });
      if (response.guard) {
        toast.warning("This question hit the prompt guard.", { position: "top-right" });
      }
      if (project.type === "rag" && response.sources && response.sources.length === 0) {
        toast.warning("No sources found. Try decreasing the score cutoff.", { position: "top-right" });
      }
    } catch (e) {
      setMessages(prev => {
        const updated = [...prev];
        const prevId = updated.length > 1 ? updated[updated.length - 2]?.id : undefined;
        updated[updated.length - 1] = {
          question: questionText,
          answer: "Error: request failed.",
          sources: [],
          id: prevId,
        };
        return updated;
      });
    } finally {
      setIsLoading(false);
      setImage(null);
      if (onQuestionSent) onQuestionSent();
    }
  }, [isLoading, streaming, project.id, auth.user.token, systemOverride, chatMode, messages, onQuestionSent, sendMessageStream]);

  const handleSend = () => {
    const text = inputText.trim();
    if (text || image) {
      sendMessage(text, image);
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
    setStreamingText("");
    setImage(null);
  };

  const showUpload = project.type === "agent" || project.type === "block";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: compact ? 500 : 600 }}>
      {/* Messages */}
      <Box sx={{ flex: 1, overflow: "auto" }} ref={scrollRef}>
          <Box sx={{ p: 2 }}>
            {messages.length === 0 && (
              <Box sx={{ textAlign: "center", mt: 4, color: "text.secondary" }}>
                <Typography variant="body2" sx={{ fontStyle: "italic" }}>
                  {systemOverride
                    ? systemOverride.substring(0, 200) + (systemOverride.length > 200 ? "..." : "")
                    : project.system
                      ? project.system.substring(0, 200) + (project.system.length > 200 ? "..." : "")
                      : "Send a message to get started."}
                </Typography>
                {project.default_prompt && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
                    Suggested: {project.default_prompt}
                  </Typography>
                )}
              </Box>
            )}
            {messages.map((msg, i) => (
              <MessageBubble key={i} message={msg} />
            ))}
            {streamingText && (
              <MessageBubble message={{ question: null, answer: streamingText, sources: [] }} />
            )}
          </Box>
      </Box>

      {/* Image preview */}
      {image && (
        <Box sx={{ px: 2, pb: 1 }}>
          <Chip
            label="Image attached"
            onDelete={() => setImage(null)}
            size="small"
            color="primary"
            variant="outlined"
          />
        </Box>
      )}

      {/* Input area */}
      <Box sx={{ display: "flex", alignItems: "flex-end", gap: 1, p: 2, borderTop: 1, borderColor: "divider" }}>
        <TextField
          fullWidth
          size="small"
          placeholder="Type a message..."
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          multiline
          maxRows={4}
          disabled={isLoading}
        />
        {showUpload && (
          <>
            <label htmlFor={`upload-${project.id}-${systemOverride ? "b" : "a"}`}>
              <Fab color="default" size="small" component="span">
                <CloudUpload fontSize="small" />
              </Fab>
            </label>
            <HiddenInput
              onChange={handleFileSelect}
              id={`upload-${project.id}-${systemOverride ? "b" : "a"}`}
              type="file"
              accept="image/*"
            />
          </>
        )}
        <Tooltip title="Clear chat">
          <Fab color="default" size="small" onClick={handleClear}>
            <DeleteSweep fontSize="small" />
          </Fab>
        </Tooltip>
        <Fab
          color="primary"
          size="small"
          onClick={handleSend}
          disabled={isLoading && !inputText.trim() && !image}
        >
          <Send fontSize="small" />
        </Fab>
      </Box>
    </Box>
  );
}
