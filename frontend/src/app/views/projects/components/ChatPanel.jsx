import { useState, useRef, useEffect, useCallback } from "react";
import {
  Box, Fab, TextField, Tooltip, Typography, Chip, styled, IconButton,
} from "@mui/material";
import { Send, CloudUpload, DeleteSweep, CallSplit, Close } from "@mui/icons-material";
import { fetchEventSource } from "@microsoft/fetch-event-source";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import MessageBubble from "./MessageBubble";

const HiddenInput = styled("input")({ display: "none" });

const url = process.env.REACT_APP_RESTAI_API_URL || "";

export default function ChatPanel({ project, systemOverride, sharedQuestion, onQuestionSent, chatMode = false, compact = false, streaming = false, context = null }) {
  const auth = useAuth();
  const [messages, setMessages] = useState([]);
  const [inputText, setInputText] = useState("");
  const [image, setImage] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [streamingText, setStreamingText] = useState("");
  const scrollRef = useRef(null);

  // Branching: each branch is { name: string, messages: array }
  // branches is empty when there's only one thread (no branching yet)
  const [branches, setBranches] = useState([]);
  const [activeBranchIdx, setActiveBranchIdx] = useState(-1); // -1 = no branches

  // Save current messages into the active branch
  const saveCurrentBranch = useCallback((currentMessages) => {
    if (activeBranchIdx >= 0) {
      setBranches(prev => prev.map((b, i) => i === activeBranchIdx ? { ...b, messages: currentMessages } : b));
    }
  }, [activeBranchIdx]);

  // Sync messages into active branch whenever they change
  useEffect(() => {
    if (activeBranchIdx >= 0 && messages.length > 0) {
      saveCurrentBranch(messages);
    }
  }, [messages]);

  const handleBranch = useCallback((messageIndex) => {
    const branchPoint = messages.slice(0, messageIndex + 1);

    if (branches.length === 0) {
      // First branch: create "Main" (full current conversation) + the new branch
      const mainBranch = { name: "Main", messages: [...messages] };
      const newNum = 1;
      const newBranch = { name: `Branch ${newNum}`, messages: [...branchPoint] };
      setBranches([mainBranch, newBranch]);
      setMessages([...branchPoint]);
      setActiveBranchIdx(1);
    } else {
      // Save current branch, then create a new one
      const newNum = branches.length;
      const newBranch = { name: `Branch ${newNum}`, messages: [...branchPoint] };
      setBranches(prev => {
        const updated = prev.map((b, i) => i === activeBranchIdx ? { ...b, messages: [...messages] } : b);
        updated.push(newBranch);
        return updated;
      });
      setMessages([...branchPoint]);
      setActiveBranchIdx(branches.length); // index of the newly pushed branch
    }
  }, [messages, branches, activeBranchIdx]);

  const switchBranch = useCallback((targetIdx) => {
    if (targetIdx === activeBranchIdx) return;
    // Save current, load target
    setBranches(prev => {
      const updated = [...prev];
      if (activeBranchIdx >= 0 && updated[activeBranchIdx]) {
        updated[activeBranchIdx] = { ...updated[activeBranchIdx], messages: [...messages] };
      }
      return updated;
    });
    setMessages([...branches[targetIdx].messages]);
    setActiveBranchIdx(targetIdx);
  }, [messages, branches, activeBranchIdx]);

  const deleteBranch = useCallback((targetIdx) => {
    setBranches(prev => {
      const updated = prev.filter((_, i) => i !== targetIdx);
      if (updated.length <= 1) {
        // Only one branch left, dissolve branching
        if (updated.length === 1) setMessages([...updated[0].messages]);
        setActiveBranchIdx(-1);
        return [];
      }
      // Adjust active index
      let newActive = activeBranchIdx;
      if (targetIdx === activeBranchIdx) {
        newActive = Math.min(targetIdx, updated.length - 1);
        setMessages([...updated[newActive].messages]);
      } else if (targetIdx < activeBranchIdx) {
        newActive = activeBranchIdx - 1;
      }
      setActiveBranchIdx(newActive);
      return updated;
    });
  }, [activeBranchIdx]);

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
    if (context) body.context = context;

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
    if (context) body.context = context;

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
    setBranches([]);
    setActiveBranchIdx(-1);
  };

  const showUpload = project.type === "agent" || project.type === "block";

  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: compact ? 500 : 600 }}>
      {/* Branch tabs */}
      {branches.length > 0 && (
        <Box sx={{ display: "flex", gap: 0.5, px: 2, py: 1, borderBottom: 1, borderColor: "divider", flexWrap: "wrap", alignItems: "center" }}>
          <CallSplit sx={{ fontSize: 16, color: "text.secondary", mr: 0.5 }} />
          {branches.map((branch, idx) => (
            <Chip
              key={idx}
              label={branch.name}
              size="small"
              color={idx === activeBranchIdx ? "primary" : "default"}
              variant={idx === activeBranchIdx ? "filled" : "outlined"}
              onClick={() => switchBranch(idx)}
              onDelete={branches.length > 2 ? () => deleteBranch(idx) : undefined}
              sx={{ fontSize: "0.75rem", height: 26 }}
            />
          ))}
        </Box>
      )}

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
              <MessageBubble
                key={`${activeBranchIdx}-${i}`}
                message={msg}
                onBranch={chatMode && msg.answer ? () => handleBranch(i) : undefined}
              />
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
