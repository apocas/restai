import { styled } from "@mui/material";
import { Image as ImageIcon } from "@mui/icons-material";
import PageHero from "app/components/page/PageHero";
import ImageChatContainer from "./components/ImageChatContainer";
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

export default function Image() {
  const auth = useAuth();
  const [generators, setGenerators] = useState([]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Image Generation";
    api.get("/image", auth.user.token)
      .then((d) => setGenerators(d.generators))
      .catch(() => {});
  }, []);

  return (
    <Container>
      <PageHero
        icon={<ImageIcon sx={{ color: "#fff" }} />}
        eyebrow="PLAYGROUND · IMAGE"
        title="Image Synthesis"
        subtitle="Generate images from a prompt, or guide an image-to-image pass with a reference plate."
        showStatusDot
        statusLabel="GPU surface"
        stats={[
          { glyph: "◆", color: "#c4b5fd", label: `${generators.length} generator${generators.length === 1 ? "" : "s"}` },
        ]}
        compact
        sx={{ mb: 2, flex: "0 0 auto" }}
      />
      <ImageChatContainer generators={generators} />
    </Container>
  );
}
