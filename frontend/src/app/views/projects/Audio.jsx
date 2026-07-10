import { styled } from "@mui/material";
import { GraphicEq } from "@mui/icons-material";
import PageHero from "app/components/page/PageHero";
import AudioChatContainer from "./components/AudioChatContainer";
import useAuth from "app/hooks/useAuth";
import { useState, useEffect } from "react";
import { topBarHeight } from "app/utils/constant";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "16px 32px",
  display: "flex",
  flexDirection: "column",
  height: `calc(100vh - ${topBarHeight + 44}px)`,
  [theme.breakpoints.down("md")]: { margin: "16px 24px" },
  [theme.breakpoints.down("sm")]: { margin: 12, height: `calc(100vh - ${topBarHeight + 24}px)` },
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
        icon={<GraphicEq sx={{ color: "#fff" }} />}
        eyebrow="PLAYGROUND · AUDIO"
        title="Audio Transcription"
        subtitle="Record or upload a clip and read it back as text, with the full engine response one click away."
        showStatusDot
        statusLabel="GPU surface"
        stats={[
          { glyph: "◆", color: "#fcd34d", label: `${generators.length} engine${generators.length === 1 ? "" : "s"}` },
        ]}
        compact
        sx={{ mb: 2, flex: "0 0 auto" }}
      />
      <AudioChatContainer generators={generators} />
    </Container>
  );
}
