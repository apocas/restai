import { useState } from "react";
import {
  Alert, Box, Button, Card, Chip, CircularProgress, TextField, Typography,
} from "@mui/material";
import { Send } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

export default function QueryPanel({ project }) {
  const auth = useAuth();
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleQuery = () => {
    if (!question.trim()) return;
    setLoading(true);
    setResult(null);
    api.post(`/projects/${project.id}/kg/query`, { question: question.trim() }, auth.user.token)
      .then(setResult)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Ask a question that mentions specific entities (people, organizations, places). The system finds matching sources and asks the LLM to answer using only those sources.
      </Typography>

      <Box sx={{ display: "flex", gap: 1, mb: 3 }}>
        <TextField
          fullWidth multiline rows={2}
          placeholder="e.g. What did the document say about Acme Corp?"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleQuery(); }}
        />
        <Button
          variant="contained" startIcon={loading ? <CircularProgress size={16} color="inherit" /> : <Send />}
          onClick={handleQuery} disabled={loading || !question.trim()}
          sx={{ alignSelf: "flex-start", minWidth: 110 }}
        >
          Ask
        </Button>
      </Box>

      {result && (
        <Card variant="outlined" sx={{ p: 3 }}>
          {result.entities_matched?.length > 0 && (
            <Box sx={{ mb: 2 }}>
              <Typography variant="caption" color="text.secondary">Entities matched</Typography>
              <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
                {result.entities_matched.map((e, i) => (
                  <Chip key={i} label={e} size="small" color="primary" variant="outlined" />
                ))}
              </Box>
            </Box>
          )}

          <Typography variant="subtitle2" sx={{ mb: 1 }}>Answer</Typography>
          <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", mb: 2 }}>
            {result.answer}
          </Typography>

          {result.sources?.length > 0 && (
            <>
              <Typography variant="caption" color="text.secondary">
                Sources ({result.source_count})
              </Typography>
              <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
                {result.sources.map((s, i) => (
                  <Chip key={i} label={s} size="small" variant="outlined" sx={{ maxWidth: 300 }} />
                ))}
              </Box>
            </>
          )}
        </Card>
      )}
    </Box>
  );
}
