import { styled, Box } from "@mui/material";
import Breadcrumb from "app/components/Breadcrumb";
import AudioChatContainer from "./components/AudioChatContainer";
import useAuth from "app/hooks/useAuth";
import { useState, useEffect } from "react";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

export default function Audio() {
  const auth = useAuth();
  const [generators, setGenerators] = useState([]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Audio Transcription";
    api.get("/audio", auth.user.token)
      .then((d) => setGenerators(d.generators))
      .catch(() => {});
  }, []);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Audio", path: "/audio" }]} />
      </Box>

      <ContentBox>
        <AudioChatContainer generators={generators} />
      </ContentBox>
    </Container>
  );
}
