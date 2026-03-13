import { Box, Divider, Fab, IconButton, MenuItem, styled, TextField, CircularProgress } from "@mui/material";
import { Delete, MoreVert, Send, CloudUpload } from "@mui/icons-material";
import { Fragment, useState } from "react";
import Scrollbar from "react-perfect-scrollbar";
import shortid from "shortid";
import ModalImage from "react-modal-image";


import MatxMenu from "app/components/MatxMenu";
import ChatAvatar from "app/components/ChatAvatar";
import { Paragraph, Span } from "app/components/Typography";
import { FlexAlignCenter, FlexBetween } from "app/components/FlexBox";
import ImageEmptyMessage from "./ImageEmptyMessage";
import useAuth from "app/hooks/useAuth";
import { useEffect } from "react";
import sha256 from 'crypto-js/sha256';
import CustomizedDialogMessage from "./CustomizedDialogMessage";
import CustomizedDialogImage from "./CustomizedDialogImage";
import { toast } from 'react-toastify';

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
    name: "A.I. Painter",
    avatar: "/admin/assets/images/painter.jpg"
  }
}) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();

  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState("");
  const [canSubmit, setCanSubmit] = useState(true);
  const [scroll, setScroll] = useState();
  const [selectedMessage, setSelectedMessage] = useState(null);
  const [selectedImage, setSelectedImage] = useState(null);
  const [image, setImage] = useState(null);
  const [state, setState] = useState({});

  const handleMessageSend = (message) => {
    handler(message);
  }

  const handler = (prompt) => {
    if(state.generator === undefined) {
      toast.error("Please select a generator");
      return;
    }

    var body = {
      "prompt": prompt
    };

    if (image && image.includes("base64,")) {
      body.image = image.split(",")[1];
    } else if (image) {
      body.image = image;
    }


    if (canSubmit) {
      setCanSubmit(false);
      setMessages([...messages, { id: body.id, prompt: prompt + " (" + state.generator + ")", input_image: image, answer: null, sources: [] }]);
      fetch(url + "/image/" + state.generator + "/generate", {
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
          if (!response.prompt) {
            response.prompt = prompt + " (" + state.generator + ")";
          }
          if(image !== null) {
            response.input_image = image;
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
      if (tempMessage !== "" || image !== null) handleMessageSend(tempMessage);
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
      <CustomizedDialogImage image={selectedImage} onclose={handleImageInfoClose} />

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
                //sx={{ minWidth: 188}}
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
            <ImageEmptyMessage />
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
                  {message.input_image && (
                    <ModalImage
                      small={message.input_image}
                      large={message.input_image}
                      alt="Input image"
                      maxHeight="200px"
                    />
                  )}
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
                  <Span sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word", cursor: 'pointer' }} value={message} onClick={() => handleClickMessage(message)}>{!message.image ? <CircularProgress size="1rem" /> : message.prompt}</Span>
                  {message.image && (
                    <ModalImage
                      small={`data:image/png;base64,${message.image}`}
                      large={`data:image/png;base64,${message.image}`}
                      alt="Output image"
                      maxHeight="200px"
                    />
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
              if (message.trim() !== "" || image !== null) handleMessageSend(message);
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
