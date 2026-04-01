import { useState, useEffect } from "react";
import { Grid } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import ProjectAnalytics from "./ProjectAnalytics";
import ProjectTokens from "./ProjectTokens";
import ProjectSourceAnalytics from "./ProjectSourceAnalytics";
import ProjectChunkingAnalytics from "./ProjectChunkingAnalytics";

export default function ProjectInfoAnalytics({ project }) {
  const auth = useAuth();
  const [tokens, setTokens] = useState({ tokens: [] });

  const now = new Date();
  const [selectedYear, setSelectedYear] = useState(now.getFullYear());
  const [selectedMonth, setSelectedMonth] = useState(now.getMonth() + 1);

  const fetchTokens = (year, month) => {
    const params = new URLSearchParams({ year, month });
    return api
      .get(
        "/projects/" + project.id + "/tokens/daily?" + params.toString(),
        auth.user.token,
        { silent: true }
      )
      .then((d) => setTokens(d.tokens))
      .catch((err) => {
        console.log(err.toString());
      });
  };

  useEffect(() => {
    if (project.name) {
      fetchTokens(selectedYear, selectedMonth);
    }
  }, [project, selectedYear, selectedMonth]);

  return (
    <Grid container spacing={3}>
      {/* Conversation analytics */}
      <Grid item xs={12}>
        <ProjectAnalytics project={project} />
      </Grid>

      {/* Token usage */}
      <Grid item xs={12}>
        <ProjectTokens
          project={project}
          tokens={tokens}
          selectedYear={selectedYear}
          selectedMonth={selectedMonth}
          setSelectedYear={setSelectedYear}
          setSelectedMonth={setSelectedMonth}
        />
      </Grid>

      {/* Source analytics (RAG only) */}
      {project.type === "rag" && (
        <Grid item xs={12}>
          <ProjectSourceAnalytics project={project} />
        </Grid>
      )}

      {/* Chunking analytics (RAG only) */}
      {project.type === "rag" && (
        <Grid item xs={12}>
          <ProjectChunkingAnalytics project={project} />
        </Grid>
      )}
    </Grid>
  );
}
