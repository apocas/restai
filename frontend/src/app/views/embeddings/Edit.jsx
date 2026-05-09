import { useState, useEffect } from "react";
import { Box, styled } from "@mui/material";
import { Hub } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import EmbeddingEdit from "./components/EmbeddingEdit";
import PageHero from "app/components/page/PageHero";
import { useParams } from "react-router-dom";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

export default function EmbeddingEditView() {
  const { id } = useParams();
  const [embedding, setEmbedding] = useState({});
  const auth = useAuth();

  useEffect(() => {
    api.get("/embeddings/" + id, auth.user.token)
      .then(setEmbedding)
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Edit Embedding - " + id;
  }, [id]);

  return (
    <Container>
      <PageHero
        icon={<Hub sx={{ color: "#fff" }} />}
        eyebrow={`EMBEDDING/${String(embedding.id || 0).padStart(4, "0")} · EDIT`}
        title={embedding.name || id}
        subtitle="Tune provider, options, dimension, and visibility for this vector encoder."
        stats={[
          { glyph: "◆", color: "#5eead4", label: embedding.class_name || "—" },
          { glyph: "▸", color: "#7dd3fc", label: embedding.privacy || "—" },
          ...(embedding.dimension
            ? [{ glyph: "⌬", color: "#a7f3d0", label: `${embedding.dimension}-d` }]
            : []),
        ]}
        compact
      />

      <Box sx={{ mt: 2.5 }}>
        {embedding.name && <EmbeddingEdit embedding={embedding} />}
      </Box>
    </Container>
  );
}
