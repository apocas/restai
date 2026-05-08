import { styled } from "@mui/material";
import { Speaker } from "@mui/icons-material";
import PageHero from "app/components/page/PageHero";
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
      <PageHero
        icon={<Speaker sx={{ color: "#fff" }} />}
        eyebrow="PLAYGROUND"
        title="Audio Playground"
        subtitle="Transcribe and generate audio."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${generators.length} engine${generators.length === 1 ? "" : "s"}` },
        ]}
        compact
      />

      <ContentBox>
        <AudioChatContainer generators={generators} />
      </ContentBox>
    </Container>
  );
}
