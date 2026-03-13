import { Box, Divider, Fab, IconButton, MenuItem, styled, TextField, CircularProgress, Tooltip } from "@mui/material";
import { Delete, MoreVert, Send, CloudUpload, MusicNote } from "@mui/icons-material";
import { Fragment, useState } from "react";
import Scrollbar from "react-perfect-scrollbar";
import shortid from "shortid";
import ReactJson from '@microlink/react-json-view';

import MatxMenu from "app/components/MatxMenu";
import ChatAvatar from "app/components/ChatAvatar";
import { Paragraph, Span } from "app/components/Typography";
import { FlexAlignCenter, FlexBetween } from "app/components/FlexBox";
import ImageEmptyMessage from "./ImageEmptyMessage";
import useAuth from "app/hooks/useAuth";
import { useEffect } from "react";
import sha256 from 'crypto-js/sha256';
import CustomizedDialogMessage from "./CustomizedDialogMessage";
import { toast } from 'react-toastify';
import { AudioRecorder } from 'react-audio-voice-recorder';

const HiddenInput = styled("input")({ display: "none" });

const ChatRoot = styled(Box)(() => ({
  height: 800,
  display: "flex",
  position: "relative",
  flexDirection: "column",
  background: "rgba(0, 0, 0, 0.05)"
}));

const LeftContent = styled(FlexBetween)(({ theme }) => ({
  padding: "4px",
  background: theme.palette.primary.main
}));

const UserName = styled("h5")(() => ({
  color: "#fff",
  fontSize: "18px",
  fontWeight: "500",
  whiteSpace: "pre",
  marginLeft: "16px"
}));

const UserStatus = styled("div")(({ theme, human }) => ({
  padding: "8px 16px",
  marginBottom: "8px",
  borderRadius: "4px",
  color: human === true && "#fff",
  background: human === true ? theme.palette.primary.main : theme.palette.background.paper
}));

const StyledItem = styled(MenuItem)(() => ({
  display: "flex",
  alignItems: "center",
  "& .icon": { marginRight: "16px" }
}));

const ScrollBox = styled(Scrollbar)(() => ({
  flexGrow: 1,
  position: "relative"
}));

const Message = styled("div")(() => ({
  display: "flex",
  alignItems: "flex-start",
  padding: "12px 16px"
}));

const MessageBox = styled(FlexAlignCenter)(() => ({
  flexGrow: 1,
  height: "100%",
  flexDirection: "column"
}));

export default function ImageChatContainer({
  generators,
  opponentUser = {
    name: "AI Musician",
    avatar: "/admin/assets/images/musician.jpg"
  }
}) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();

  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState("");
  const [canSubmit, setCanSubmit] = useState(true);
  const [scroll, setScroll] = useState();
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [file, setFile] = useState(null);
  const [state, setState] = useState({});
  const [expandedChunks, setExpandedChunks] = useState(null);
  const [language, setLanguage] = useState("");

  const handleMessageSend = (message) => {
    handler(message);
  }

  const record_complete = (blob) => {
    setFile(blob);
  }

  const handler = (prompt) => {
    if (state.generator === undefined) {
      toast.error("Please select a generator");
      return;
    }

    var body = {
      "prompt": prompt
    };

    if (canSubmit) {
      setCanSubmit(false);

      const formData = new FormData();
      formData.append("file", file);
      formData.append("prompt", prompt);
      formData.append("language", language);

      setMessages([...messages, { id: body.id, prompt: prompt + " (" + state.generator + ")", input_audio: file, answer: null, sources: [] }]);
      fetch(url + "/audio/" + state.generator + "/transcript", {
        method: 'POST',
        headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }),
        body: formData,
      })
        .then(function (response) {
          if (!response.ok) {
            response.json().then(function (data) {
              toast.error(data.detail);
            });
            throw Error(response.statusText);
          } else {
            return response.json();
          }
        })
        .then((response) => {
          if (!response.prompt) {
            response.prompt = prompt + " (" + state.generator + ")";
          }
          if (file !== null) {
            response.input_audio = file;
          }
          setMessages([...messages, response]);
          setCanSubmit(true);
        }).catch(err => {
          toast.error(err.toString());
          setMessages([...messages, { id: null, prompt: prompt, answer: "Error, something went wrong with my transistors.", sources: [] }]);
          setCanSubmit(true);
        });
    }
  }

  const handleClickMessage = (message) => {
    setSelectedMessage(message);
  }

  const handleMessageInfoClose = () => {
    setSelectedMessage(null);
  }

  const sendMessageOnEnter = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      let tempMessage = message.trim();
      if (tempMessage !== "" || file !== null) handleMessageSend(tempMessage);
      setMessage("");
    }
  };

  const handleFileSelect = async (event) => {
    if (event.target.files.length === 1) {
      let file = event.target.files[0];
      setFile(file);
    }
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  useEffect(() => {
    if (scroll) {
      scroll.scrollTop = Number.MAX_SAFE_INTEGER
    }
  }, [messages]);

  return (
    <ChatRoot>
      <CustomizedDialogMessage message={selectedMessage} onclose={handleMessageInfoClose} />

      <LeftContent>
        <Box display="flex" alignItems="center" pl={2}>
          <Fragment>
            <ChatAvatar src={opponentUser.avatar} />
            <UserName>
              <TextField
                select
                size="small"
                name="generator"
                label="Generator"
                variant="outlined"
                onChange={handleChange}
                sx={{
                  minWidth: 188,
                  "& .MuiOutlinedInput-notchedOutline": {
                    border: "2px solid white"
                  },
                  "& .MuiOutlinedInput-root": {
                    "&.Mui-focused fieldset": {
                      border: "2px solid white"
                    }
                  },
                  "& .MuiInputLabel-root": {
                    color: "white"
                  },
                  "& .MuiSelect-select": {
                    color: "white"
                  },
                  "& .MuiSelect-icon": {
                    color: "white"
                  }
                }}
              >
                {generators.map((item, ind) => (
                  <MenuItem value={item} key={item}>
                    {item}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                size="small"
                name="language"
                label="Language"
                variant="outlined"
                value={language}
                onChange={e => setLanguage(e.target.value)}
                sx={{
                  minWidth: 120,
                  marginLeft: 2,
                  "& .MuiOutlinedInput-notchedOutline": {
                    border: "2px solid white"
                  },
                  "& .MuiOutlinedInput-root": {
                    "&.Mui-focused fieldset": {
                      border: "2px solid white"
                    }
                  },
                  "& .MuiInputLabel-root": {
                    color: "white"
                  },
                  "& .MuiInputBase-input": {
                    color: "white"
                  }
                }}
              />
            </UserName>
          </Fragment>
        </Box>


        <Box>
          <MatxMenu
            menuButton={
              <IconButton size="large" sx={{ verticalAlign: "baseline !important" }}>
                <MoreVert sx={{ color: "#fff" }} />
              </IconButton>
            }>

            <StyledItem>
              <Delete className="icon" /> Clear Chat
            </StyledItem>
          </MatxMenu>
        </Box>
      </LeftContent>

      <ScrollBox id="chat-message-list" containerRef={setScroll}>
        {messages.length === 0 && (
          <MessageBox>
            <ImageEmptyMessage image={"/admin/assets/images/music.jpg"} />
            <p>Write or send something...</p>
            <p>(This isn't a chat/agent, there is no memory/conversation)</p>
          </MessageBox>
        )}

        {messages.map((message, index) => (
          <Fragment>
            <Message key={shortid.generate()}>
              <ChatAvatar src={"https://www.gravatar.com/avatar/" + sha256(auth.user.username)} />

              <Box ml={2}>
                <Paragraph m={0} mb={1} color="text.secondary">
                  {"Me"}
                </Paragraph>

                <UserStatus human={true} >
                  <Span sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{message.prompt}</Span>
                  {
                    message.input_audio &&
                    <>
                      {message.input_audio.name || "Microphone"}

                      <Box>
                        <audio
                          src={URL.createObjectURL(message.input_audio)}
                          controls
                        />
                      </Box>
                    </>
                  }
                </UserStatus>
              </Box>
            </Message>

            <Message key={shortid.generate()}>
              <ChatAvatar src={opponentUser.avatar} />

              <Box ml={2}>
                <Paragraph m={0} mb={1} color="text.secondary">
                  {opponentUser.name}
                </Paragraph>

                <UserStatus human={false} >
                  <Span sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", cursor: 'pointer' }} value={message} onClick={() => handleClickMessage(message)}>{!message.answer ? <CircularProgress size="1rem" /> : message.answer.text}</Span>
                  {/* Render answer.chunks or answer.segments as JSON if present */}
                  {message.answer && (Array.isArray(message.answer.chunks)) && (
                    <Box mt={2}>
                      <ReactJson
                        src={message.answer.chunks || message.answer.segments}
                        name={Array.isArray(message.answer.chunks) ? 'chunks' : 'segments'}
                        collapsed={1}
                        enableClipboard={true}
                        displayDataTypes={false}
                        style={{ fontSize: '0.9em', background: '#f5f5f5', borderRadius: 8, padding: 8 }}
                      />
                      {message.answer.word_chunks && (
                        <Box mt={2}>
                          <ReactJson
                            src={message.answer.word_chunks}
                            name="word_chunks"
                            collapsed={1}
                            enableClipboard={true}
                            displayDataTypes={false}
                            style={{ fontSize: '0.9em', background: '#f5f5f5', borderRadius: 8, padding: 8 }}
                          />
                        </Box>
                      )}
                    </Box>
                  )}
                </UserStatus>
              </Box>
            </Message>
          </Fragment>
        ))}
      </ScrollBox>

      <Divider />

      <Box px={2} py={1} display="flex" alignItems="center">
        <TextField
          rows={1}
          fullWidth
          value={message}
          multiline={true}
          variant="outlined"
          onKeyUp={sendMessageOnEnter}
          label="Type your prompt here..."
          onChange={(e) => setMessage(e.target.value)}
          sx={{ marginRight: 2 }}
        />

        <div style={{ display: "flex" }}>
          {file !== null && (
            <Box
              sx={{
                height: 56,
              }}
            >
              <Tooltip title={"Audio loaded. " + (file.name || "Microphone")}>
                <MusicNote sx={{ fontSize: '3.5rem', color: '#4CAF50' }} />
              </Tooltip>
            </Box>
          )}
          <AudioRecorder
            onRecordingComplete={record_complete}
            audioTrackConstraints={{
              noiseSuppression: true,
              echoCancellation: true,
            }}
            onNotAllowedOrFound={(err) => console.table(err)}
            downloadOnSavePress={false}
            downloadFileExtension="webm"
            mediaRecorderOptions={{
              audioBitsPerSecond: 128000,
            }}
          />
          <Fragment>
            <label htmlFor="upload-single-file">
              <Fab
                color="primary"
                sx={{ ml: 2 }} component="span">
                <CloudUpload />
              </Fab>
            </label>
            <HiddenInput onChange={handleFileSelect} id="upload-single-file" type="file" />
          </Fragment>
          <Fab
            onClick={() => {
              if (message.trim() !== "" || file !== null) handleMessageSend(message);
              setMessage("");
            }}
            color="primary"
            sx={{ ml: 2 }}>
            <Send />
          </Fab>
        </div>
      </Box>

    </ChatRoot>
  );
}
