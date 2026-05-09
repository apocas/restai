import { useState, useEffect } from "react";
import { Box, styled } from "@mui/material";
import { Hub } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import EmbeddingInfo from "./components/EmbeddingInfo";
import PageHero from "app/components/page/PageHero";
import { useParams } from "react-router-dom";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

export default function EmbeddingViewInfo() {
  const { id } = useParams();
  const [projects, setProjects] = useState([]);
  const [embedding, setEmbedding] = useState({});
  const [info, setInfo] = useState({ version: "", embeddings: [], llms: [], loaders: [] });
  const auth = useAuth();

  const fetchEmbedding = (name) =>
    api.get("/embeddings/" + name, auth.user.token)
      .then((d) => setEmbedding(d))
      .catch(() => {});

  const fetchProjects = () =>
    api.get("/projects", auth.user.token)
      .then((d) => setProjects(d.projects || []))
      .catch(() => {});

  const fetchInfo = () =>
    api.get("/info", auth.user.token)
      .then(setInfo)
      .catch(() => {});

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Embedding - " + id;
    fetchEmbedding(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => {
    fetchProjects();
    fetchInfo();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Count how many projects use this embedding model.
  const usedBy = (projects || []).filter((p) => p.embeddings === embedding.name).length;

  return (
    <Container>
      <PageHero
        icon={<Hub sx={{ color: "#fff" }} />}
        eyebrow={`EMBEDDING/${String(embedding.id || 0).padStart(4, "0")}`}
        title={embedding.name || id}
        subtitle={embedding.description || "Vector encoder for semantic search and retrieval."}
        stats={[
          { glyph: "◆", color: "#5eead4", label: embedding.class_name || "—" },
          { glyph: "▸", color: "#7dd3fc", label: embedding.privacy || "—" },
          ...(embedding.dimension
            ? [{ glyph: "⌬", color: "#a7f3d0", label: `${embedding.dimension}-d` }]
            : []),
          ...(usedBy > 0
            ? [{ glyph: "★", color: "#fcd34d", label: `${usedBy} project${usedBy === 1 ? "" : "s"}` }]
            : []),
        ]}
        compact
      />

      <Box sx={{ mt: 2.5 }}>
        {embedding.name && (
          <EmbeddingInfo embedding={embedding} projects={projects} info={info} usedBy={usedBy} />
        )}
      </Box>
    </Container>
  );
}
