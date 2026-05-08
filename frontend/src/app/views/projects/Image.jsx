import { styled } from "@mui/material";
import { Image as ImageIcon } from "@mui/icons-material";
import PageHero from "app/components/page/PageHero";
import ImageChatContainer from "./components/ImageChatContainer";
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
        eyebrow="PLAYGROUND"
        title="Image Playground"
        subtitle="Generate images using configured generators."
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${generators.length} generator${generators.length === 1 ? "" : "s"}` },
        ]}
        compact
      />

      <ContentBox>
        <ImageChatContainer generators={generators} />
      </ContentBox>
    </Container>
  );
}
