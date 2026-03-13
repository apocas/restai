import { Box, Divider, Fab, IconButton, MenuItem, styled, TextField, CircularProgress, useTheme, Tooltip } from "@mui/material";
import { AccountCircle, Delete, MoreVert, Send, CloudUpload, Cast, Chat } from "@mui/icons-material";
import { Fragment, useState, useRef } from "react";
import Scrollbar from "react-perfect-scrollbar";
import shortid from "shortid";
import { fetchEventSource } from '@microsoft/fetch-event-source';
import ModalImage from "react-modal-image";


import MatxMenu from "app/components/MatxMenu";
import ChatAvatar from "app/components/ChatAvatar";
import { Paragraph, Span } from "app/components/Typography";
import { FlexAlignCenter, FlexBetween } from "app/components/FlexBox";
import EmptyMessage from "./EmptyMessage";
import useAuth from "app/hooks/useAuth";
import { useEffect } from "react";
import sha256 from 'crypto-js/sha256';
import CustomizedDialogMessage from "./CustomizedDialogMessage";
import CustomizedDialogImage from "./CustomizedDialogImage";
import { toast } from 'react-toastify';
import Terminal from "./Terminal";


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

const SystemMessage = styled("div")(() => ({
  display: "flex",
  alignItems: "flex-start",
  padding: "20px 100px 0px 100px",
  whiteSpace: "pre-wrap"
}));

const MessageBox = styled(FlexAlignCenter)(() => ({
  flexGrow: 1,
  height: "100%",
  flexDirection: "column"
}));

export default function ChatContainer({
  project,
  opponent = {
    name: "A.I.",
    avatar: "/admin/assets/images/bot.jpg"
  }
}) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();

  const [messages, setMessages] = useState([]);
  const [chunks, setChunks] = useState([]);
  const [message, setMessage] = useState("");
  const [canSubmit, setCanSubmit] = useState(true);
  const [scroll, setScroll] = useState();
  const [chat, setChat] = useState(true);
  const [stream, setStream] = useState(false);
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [selectedImage, setSelectedImage] = useState(null);
  const [image, setImage] = useState(null);

  const { palette } = useTheme();

  const handleMessageSend = (message) => {
    if (stream === true) {
      handlerStream(message);
    } else {
      handler(message);
    }
  }

  const handlerStream = (question) => {
    var endpoint = "question";

    var body = {
      "question": question
    };

    if (image && image.includes("base64,")) {
      body.image = image.split(",")[1];
    } else if (image) {
      body.image = image;
    }

    if (chat === true) {
      if (messages.length !== 0) {
        body.id = messages[messages.length - 1].id
      }
      endpoint = "chat";
    }

    body.stream = true;
    setChunks([]);

    if (canSubmit) {
      setCanSubmit(false);
      fetchEventSource(url + "/projects/" + project.id + "/" + endpoint, {
        method: "POST",
        headers: { 'Accept': 'text/event-stream', 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token },
        body: JSON.stringify(body),
        onopen(res) {
          if (res.ok && res.status === 200) {
            console.log("Connection made ", res);
          } else if (res.status >= 400 && res.status < 500 && res.status !== 429) {
            console.log("Client-side error ", res);
          }
        },
        onmessage(event) {
          if (event.event === "close" || event.event === "error") {
            if (event.event === "error") {
              toast.error(event.data);
              setMessages([...messages, { id: null, question: question, answer: "Error, something went wrong with my transistors.", sources: [] }]);
              setCanSubmit(true);
            } else {
              setChunks((chunks) => [...chunks, event.data]);
            }
          } else {
            setChunks((chunks) => [...chunks, event.data]);
            console.log(chunks);
          }

        },
        onclose() {
          console.log("Connection closed by the server");
        },
        onerror(err) {
          console.log("There was an error from server", err);
        },
      });
    }
  }

  const handler = (question) => {
    var endpoint = "question";

    var body = {
      "question": question
    };

    if (image && image.includes("base64,")) {
      body.image = image.split(",")[1];
    } else if (image) {
      body.image = image;
    }

    if (chat === true) {
      if (messages.length !== 0) {
        body.id = messages[messages.length - 1].id
      }
      endpoint = "chat";
    }

    if (canSubmit) {
      setCanSubmit(false);
      setMessages([...messages, { id: body.id, question: question, answer: null, sources: [] }]);
      fetch(url + "/projects/" + project.id + "/" + endpoint, {
        method: 'POST',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
        body: JSON.stringify(body),
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
          if (project.type === "vision" && !response.image) {
            response.image = image;
          }
          setMessages([...messages, response]);
          setCanSubmit(true);
          if (response.guard === true) {
            toast.warning('This question hit the prompt guard. Sandbox message sent.', { duration: 6000, position: 'top-right' });
          } else if (project.type === "rag" && response.sources.length === 0) {
            toast.warning('No sources found for this question. Decrease the score cutoff parameter.', { duration: 6000, position: 'top-right' });
          }
        }).catch(err => {
          toast.error(err.toString());
          setMessages([...messages, { id: null, question: question, answer: "Error, something went wrong with my transistors.", sources: [] }]);
          setCanSubmit(true);
        });
    }
  }

  const handleClickStream = (event) => {
    setStream(!stream);
  }

  const handleClickChat = (event) => {
    setChat(!chat);
  }

  const handleClickMessage = (message) => {
    setSelectedMessage(message);
  }

  const handleClickImage = (image) => {
    setSelectedImage(image);
  }

  const handleMessageInfoClose = () => {
    setSelectedMessage(null);
  }

  const handleImageInfoClose = () => {
    setSelectedImage(null);
  }

  const sendMessageOnEnter = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      let tempMessage = message.trim();
      if (tempMessage !== "") handleMessageSend(tempMessage);
      setMessage("");
    }
  };

  const convertToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const fileReader = new FileReader();
      fileReader.readAsDataURL(file);
      fileReader.onload = () => {
        resolve(fileReader.result);
      };
      fileReader.onerror = (error) => {
        reject(error);
      };
    });
  };

  const handleFileSelect = async (event) => {
    if (event.target.files.length === 1) {
      let file = event.target.files[0];
      const base64 = await convertToBase64(file);
      setImage(base64);
    }
  };

  useEffect(() => {
    if (chunks[chunks.length - 1] && JSON.parse(chunks[chunks.length - 1]).answer !== undefined) {
      var info = JSON.parse(chunks.pop());
      setMessages([...messages, info]);
      setChunks([]);
      setCanSubmit(true);
      if (info.guard === true) {
        toast.warning('This question hit the prompt guard. Sandbox message sent.', { duration: 6000, position: 'top-right' });
      } else if (project.type === "rag" && info.sources.length === 0) {
        toast.warning('No sources found for this question. Decrease the score cutoff parameter.', { duration: 6000, position: 'top-right' });
      }
    }
  }, [chunks]);


  useEffect(() => {
    if (scroll) {
      scroll.scrollTop = Number.MAX_SAFE_INTEGER
    }
  }, [messages]);

  useEffect(() => {
    if (project.type === "vision" || project.type === "router") {
      setChat(false);
    }
    if (project.default_prompt) {
      setMessage(project.default_prompt);
    }
  }, [project]);

  return (
    <ChatRoot>
      <CustomizedDialogMessage message={selectedMessage} onclose={handleMessageInfoClose} />
      <CustomizedDialogImage image={selectedImage} onclose={handleImageInfoClose} />

      <LeftContent>
        <Box display="flex" alignItems="center" pl={2}>
          <Fragment>
            <ChatAvatar src={opponent.avatar} />
            <UserName>{project.name} ({project.llm})</UserName>
          </Fragment>
        </Box>


        <Box display="flex" alignItems="center">
          <Cast sx={{ color: stream ? palette.success.light : palette.error.main }} />
          <Tooltip title={chat ? "Chat mode" : "QA mode"} ml={3}>
            <Chat sx={{ color: chat ? palette.success.light : palette.error.main, ml: 2 }} />
          </Tooltip>
          <MatxMenu
            menuButton={
              <IconButton size="large" sx={{ verticalAlign: "baseline !important" }}>
                <MoreVert sx={{ color: "#fff" }} />
              </IconButton>
            }>

            <StyledItem onClick={handleClickStream}>
              <AccountCircle className="icon" /> {stream ? "Disable Streaming" : "Enable Streaming"}
            </StyledItem>

            <StyledItem onClick={handleClickChat}>
              <AccountCircle className="icon" /> {chat ? "QA Mode" : "Chat Mode"}
            </StyledItem>

            <StyledItem>
              <Delete className="icon" /> Clear Chat
            </StyledItem>
          </MatxMenu>
        </Box>
      </LeftContent>

      <ScrollBox id="chat-message-list" containerRef={setScroll}>
        {messages.length === 0 && chunks.length === 0 && (
          <MessageBox>
            <EmptyMessage />
            <SystemMessage>{project.system}</SystemMessage>
            <p>Write something...</p>
          </MessageBox>
        )}

        {messages.map((message, index) => (
          <Fragment key={message.id || index}>
            <Message>
              <ChatAvatar src={"https://www.gravatar.com/avatar/" + sha256(auth.user.username)} />

              <Box ml={2}>
                <Paragraph m={0} mb={1} color="text.secondary">
                  {"Me"}
                </Paragraph>

                <UserStatus human={true} >
                  <Span sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{message.question}</Span>
                </UserStatus>
              </Box>
            </Message>

            <Message>
              <ChatAvatar src={opponent.avatar} />

              <Box ml={2}>
                <Paragraph m={0} mb={1} color="text.secondary">
                  {opponent.name}
                </Paragraph>

                <UserStatus human={false} >
                  {image && (
                    <ModalImage
                      small={message.image}
                      large={message.image}
                      maxheight={50}
                    />
                  )}
                  {message.reasoning && message.reasoning.steps.length > 0 && message.reasoning.steps[message.reasoning.steps.length - 1].actions.length && (
                    <Terminal message={message}
                    >
                    </Terminal>
                  )}
                  <Span sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", cursor: 'pointer' }} value={message} onClick={() => handleClickMessage(message)}>{!message.answer ? <CircularProgress size="1rem" /> : message.answer}</Span>
                </UserStatus>
              </Box>
            </Message>
          </Fragment>
        ))}
        {chunks.length > 0 &&
          <Fragment>
            <Message key={shortid.generate()}>
              <ChatAvatar src={opponent.avatar} />

              <Box ml={2}>
                <Paragraph m={0} mb={1} color="text.secondary">
                  {opponent.name}
                </Paragraph>

                <UserStatus human={false} >
                  <Span sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{chunks.map(answer => {
                    const parsedAnswer = JSON.parse(answer);
                    return parsedAnswer.text !== undefined ? parsedAnswer.text : '';
                  }).join('')}</Span>
                </UserStatus>
              </Box>
            </Message>
          </Fragment>
        }
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
          label={"Type your message here..."}
          onChange={(e) => setMessage(e.target.value)}
        />

        <div style={{ display: "flex" }}>
          {image !== null && (
            <Box
              component="img"
              sx={{
                height: 56,
              }}
              alt="Image preview"
              src={image}
              onClick={() => handleClickImage(image)}
            />
          )}
          {project.type === "vision" && (
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
          )}
          <Fab
            onClick={() => {
              if (message.trim() !== "") handleMessageSend(message);
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
