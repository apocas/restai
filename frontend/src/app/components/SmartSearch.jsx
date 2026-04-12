import { useState, useEffect, useRef } from "react";
import {
  Box,
  Button,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import AssignmentIcon from "@mui/icons-material/Assignment";
import PersonIcon from "@mui/icons-material/Person";
import GroupsIcon from "@mui/icons-material/Groups";
import PsychologyIcon from "@mui/icons-material/Psychology";
import HubIcon from "@mui/icons-material/Hub";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const SUGGESTIONS = [
  "rag projects using gpt-4",
  "restricted users",
  "public llms",
  "agent projects in team engineering",
  "admin users",
];

const LOADING_MESSAGES = [
  "Asking the AI...",
  "Translating your query...",
  "Understanding what you mean...",
  "Searching the database...",
];

const ENTITY_LABELS = {
  projects: "Project",
  users: "User",
  teams: "Team",
  llms: "LLM",
  embeddings: "Embedding",
};

const ENTITY_ICONS = {
  projects: AssignmentIcon,
  users: PersonIcon,
  teams: GroupsIcon,
  llms: PsychologyIcon,
  embeddings: HubIcon,
};

export default function SmartSearch({ open, onClose }) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingMessage, setLoadingMessage] = useState(LOADING_MESSAGES[0]);
  const [results, setResults] = useState([]);
  const [structured, setStructured] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const [note, setNote] = useState(null);
  const [error, setError] = useState(null);
  const navigate = useNavigate();
  const auth = useAuth();
  const inputRef = useRef(null);

  useEffect(() => {
    if (open) {
      const t = setTimeout(() => {
        if (inputRef.current) inputRef.current.focus();
      }, 100);
      return () => clearTimeout(t);
    }
    setQuery("");
    setResults([]);
    setStructured(null);
    setWarnings([]);
    setNote(null);
    setError(null);
  }, [open]);

  useEffect(() => {
    if (!loading) return;
    let i = 0;
    setLoadingMessage(LOADING_MESSAGES[0]);
    const interval = setInterval(() => {
      i = (i + 1) % LOADING_MESSAGES.length;
      setLoadingMessage(LOADING_MESSAGES[i]);
    }, 1400);
    return () => clearInterval(interval);
  }, [loading]);

  const runSearch = (q) => {
    const text = (q != null ? q : query).trim();
    if (!text) return;
    setLoading(true);
    setError(null);
    setResults([]);
    setStructured(null);
    setWarnings([]);
    setNote(null);

    const startedAt = Date.now();
    const MIN_LOADING_MS = 800;

    const finish = (apply) => {
      const elapsed = Date.now() - startedAt;
      const remaining = Math.max(0, MIN_LOADING_MS - elapsed);
      setTimeout(() => {
        apply();
        setLoading(false);
      }, remaining);
    };

    api
      .post("/search", { query: text }, auth.user.token)
      .then((d) => {
        finish(() => {
          setResults(d.results || []);
          setStructured(d.query || null);
          setWarnings(d.warnings || []);
          setNote(d.note || null);
        });
      })
      .catch((err) => {
        finish(() => {
          setError((err && err.detail) || "Search failed");
          setResults([]);
        });
      });
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      runSearch();
    }
  };

  const handleNavigate = (path) => {
    onClose();
    navigate(path);
  };

  const formatFilter = (f) => `${f.field} ${f.op} ${JSON.stringify(f.value)}`;

  return (
    <Dialog
      open={open}
      onClose={onClose}
      fullWidth
      maxWidth="sm"
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle sx={{ pb: 1 }}>Smart Search</DialogTitle>

      <Box sx={{ px: 3, pb: 2 }}>
        <TextField
          inputRef={inputRef}
          fullWidth
          size="small"
          placeholder="Search anything... e.g. 'rag projects using gpt-4'"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading}
        />
      </Box>

      <DialogContent sx={{ p: 0, pt: 0, minHeight: 240, maxHeight: 520 }}>
        {loading && (
          <Box
            sx={{
              px: 3,
              py: 5,
              textAlign: "center",
            }}
          >
            <Typography variant="body2" color="text.secondary">
              {loadingMessage}
            </Typography>
          </Box>
        )}

        {!loading && !query && results.length === 0 && !error && (
          <Box sx={{ px: 3, py: 2 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ textTransform: "uppercase", fontWeight: 700, letterSpacing: 0.5 }}
            >
              Try
            </Typography>
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 1, mt: 1.5 }}>
              {SUGGESTIONS.map((s) => (
                <Chip
                  key={s}
                  label={s}
                  variant="outlined"
                  size="small"
                  clickable
                  onClick={() => {
                    setQuery(s);
                    runSearch(s);
                  }}
                />
              ))}
            </Box>
          </Box>
        )}

        {!loading && error && (
          <Box sx={{ px: 3, py: 3 }}>
            <Typography variant="body2" color="error">
              {error}
            </Typography>
          </Box>
        )}

        {!loading && results.length > 0 && (
          <Box>
            {structured && (
              <Box
                sx={{
                  px: 3,
                  py: 1.25,
                  borderBottom: "1px solid",
                  borderColor: "divider",
                }}
              >
                <Typography variant="caption" color="text.secondary">
                  Searching <strong>{structured.entity}</strong>
                  {structured.filters && structured.filters.length > 0 && " where "}
                  {structured.filters &&
                    structured.filters.map((f, i) => (
                      <Box
                        key={i}
                        component="span"
                        sx={{ fontFamily: "monospace", ml: 0.5 }}
                      >
                        {i > 0 ? " AND " : ""}
                        {formatFilter(f)}
                      </Box>
                    ))}
                </Typography>
              </Box>
            )}

            {note && (
              <Box
                sx={{
                  px: 3,
                  py: 1.25,
                  borderBottom: "1px solid",
                  borderColor: "divider",
                }}
              >
                <Typography variant="caption" color="warning.main">
                  {note}
                </Typography>
              </Box>
            )}

            <Box>
              {results.map((r, i) => (
                <Button
                  key={`${r.entity}-${r.id}-${i}`}
                  onClick={() => handleNavigate(r.path)}
                  fullWidth
                  sx={{
                    justifyContent: "flex-start",
                    textTransform: "none",
                    borderRadius: 0,
                    borderBottom: "1px solid",
                    borderColor: "divider",
                    px: 3,
                    py: 1.5,
                    color: "text.primary",
                  }}
                >
                  {(() => { const Icon = ENTITY_ICONS[r.entity] || SearchIcon; return <Icon fontSize="small" sx={{ mr: 1.5, color: "text.secondary" }} />; })()}
                  <Box sx={{ flex: 1, textAlign: "left" }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                      <Chip
                        label={ENTITY_LABELS[r.entity] || r.entity}
                        size="small"
                        variant="outlined"
                        sx={{ height: 20, fontSize: "0.68rem" }}
                      />
                      <Typography variant="body2" fontWeight={600}>
                        {r.name}
                      </Typography>
                    </Box>
                    {r.subtitle && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: "block", mt: 0.25 }}
                      >
                        {r.subtitle}
                      </Typography>
                    )}
                  </Box>
                </Button>
              ))}
            </Box>

            {warnings.length > 0 && (
              <Box
                sx={{
                  px: 3,
                  py: 1.25,
                  borderTop: "1px solid",
                  borderColor: "divider",
                }}
              >
                {warnings.map((w, i) => (
                  <Typography
                    key={i}
                    variant="caption"
                    color="warning.main"
                    sx={{ display: "block" }}
                  >
                    {w}
                  </Typography>
                ))}
              </Box>
            )}
          </Box>
        )}

        {!loading && query && !error && results.length === 0 && structured && (
          <Box sx={{ px: 3, py: 4, textAlign: "center" }}>
            <Typography variant="body2" color="text.secondary">
              No results matching your query.
            </Typography>
          </Box>
        )}
      </DialogContent>
    </Dialog>
  );
}
