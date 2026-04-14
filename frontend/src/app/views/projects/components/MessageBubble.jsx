import { useState } from "react";
import {
  Box, Chip, Collapse, IconButton, Typography, styled, Tooltip,
  Accordion, AccordionSummary, AccordionDetails,
} from "@mui/material";
import { ContentCopy, ExpandMore, Shield, Cached, Speed, TerminalOutlined, CallSplit } from "@mui/icons-material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Terminal from "./Terminal";

const QuestionBubble = styled(Box)(({ theme }) => ({
  backgroundColor: theme.palette.primary.main,
  color: "#fff",
  padding: "10px 16px",
  borderRadius: "16px 16px 4px 16px",
  maxWidth: "80%",
  marginLeft: "auto",
  wordBreak: "break-word",
  whiteSpace: "pre-wrap",
}));

const AnswerBubble = styled(Box)(({ theme }) => ({
  backgroundColor: theme.palette.mode === "dark" ? "#2d2d2d" : "#f5f5f5",
  padding: "10px 16px",
  borderRadius: "16px 16px 16px 4px",
  maxWidth: "80%",
  wordBreak: "break-word",
  "& table": {
    borderCollapse: "collapse",
    width: "100%",
    margin: "8px 0",
    fontSize: "0.85rem",
  },
  "& th, & td": {
    border: `1px solid ${theme.palette.divider}`,
    padding: "6px 10px",
    textAlign: "left",
  },
  "& th": {
    backgroundColor: theme.palette.mode === "dark" ? "#383838" : "#e8e8e8",
    fontWeight: 600,
  },
  "& pre": {
    backgroundColor: theme.palette.mode === "dark" ? "#1e1e1e" : "#e0e0e0",
    padding: "10px",
    borderRadius: "6px",
    overflowX: "auto",
    fontSize: "0.82rem",
    margin: "8px 0",
  },
  "& code": {
    fontFamily: "'JetBrains Mono', 'SF Mono', Monaco, Consolas, monospace",
    fontSize: "0.85em",
  },
  "& :not(pre) > code": {
    backgroundColor: theme.palette.mode === "dark" ? "#383838" : "#e0e0e0",
    padding: "2px 5px",
    borderRadius: "4px",
  },
  "& p": { margin: "4px 0" },
  "& ul, & ol": { margin: "4px 0", paddingLeft: "20px" },
  "& h1, & h2, & h3, & h4, & h5, & h6": { margin: "8px 0 4px" },
  "& hr": { border: "none", borderTop: `1px solid ${theme.palette.divider}`, margin: "8px 0" },
  "& a": { color: theme.palette.primary.main },
}));

export default function MessageBubble({ message, onBranch }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    if (message.answer) {
      navigator.clipboard.writeText(message.answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }
  };

  return (
    <Box sx={{ mb: 2 }}>
      {/* Question */}
      {(message.question || message._image) && (
        <Box sx={{ display: "flex", justifyContent: "flex-end", mb: 1 }}>
          <QuestionBubble>
            {message._image && (
              <Box
                component="img"
                src={message._image}
                sx={{ maxWidth: "100%", maxHeight: 200, borderRadius: 1, mb: message.question ? 1 : 0, display: "block" }}
              />
            )}
            {message.question && (
              <Typography variant="body2">{message.question}</Typography>
            )}
          </QuestionBubble>
        </Box>
      )}

      {/* Answer */}
      {message.answer !== null && message.answer !== undefined && (
        <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
          <Box sx={{ maxWidth: "80%" }}>
            <AnswerBubble>
              <Typography variant="body2" component="div">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.answer}</ReactMarkdown>
              </Typography>
              {/* Agent reasoning — collapsed inside the bubble */}
              {message.reasoning && message.reasoning.steps && message.reasoning.steps.length > 0 && (
                <Accordion
                  disableGutters
                  elevation={0}
                  defaultExpanded={false}
                  sx={{ mt: 1, backgroundColor: "transparent", "&:before": { display: "none" } }}
                >
                  <AccordionSummary expandIcon={<ExpandMore />} sx={{ minHeight: 32, px: 0, "& .MuiAccordionSummary-content": { my: 0 } }}>
                    <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                      <TerminalOutlined fontSize="small" />
                      <Typography variant="caption" color="text.secondary">
                        {message.reasoning.steps.length} reasoning step{message.reasoning.steps.length !== 1 ? "s" : ""}
                      </Typography>
                    </Box>
                  </AccordionSummary>
                  <AccordionDetails sx={{ px: 0, pt: 0 }}>
                    <Terminal message={message} />
                  </AccordionDetails>
                </Accordion>
              )}

              {/* Sources — inside the bubble */}
              {message.sources && message.sources.length > 0 && (
                <Accordion
                disableGutters
                elevation={0}
                sx={{ mt: 1, backgroundColor: "transparent", "&:before": { display: "none" } }}
              >
                <AccordionSummary expandIcon={<ExpandMore />} sx={{ minHeight: 32, px: 0, "& .MuiAccordionSummary-content": { my: 0 } }}>
                  <Typography variant="caption" color="text.secondary">
                    {message.sources.length} source{message.sources.length !== 1 ? "s" : ""}
                  </Typography>
                </AccordionSummary>
                <AccordionDetails sx={{ px: 0, pt: 0 }}>
                  {message.sources.map((src, i) => (
                    <Box key={i} sx={{ mb: 1, p: 1, borderRadius: 1, backgroundColor: "action.hover" }}>
                      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.5 }}>
                        <Typography variant="caption" fontWeight="bold">
                          {src.source || `Source ${i + 1}`}
                        </Typography>
                        {src.score !== undefined && (
                          <Chip label={`${(src.score * 100).toFixed(0)}%`} size="small" />
                        )}
                      </Box>
                      <Typography variant="caption" color="text.secondary" sx={{ display: "block", whiteSpace: "pre-wrap" }}>
                        {typeof src === "string" ? src : (src.text || JSON.stringify(src))}
                      </Typography>
                    </Box>
                  ))}
                </AccordionDetails>
              </Accordion>
              )}
            </AnswerBubble>

            {/* Metadata chips — outside bubble */}
            <Box sx={{ display: "flex", gap: 0.5, mt: 0.5, flexWrap: "wrap", alignItems: "center" }}>
              {message.guard && (
                <Chip icon={<Shield />} label="Guard" size="small" color="warning" variant="outlined" />
              )}
              {message.cached && (
                <Chip icon={<Cached />} label="Cached" size="small" color="info" variant="outlined" />
              )}
              {message.tokens && (message.tokens.input > 0 || message.tokens.output > 0) && (
                <Chip
                  label={`${message.tokens.input + message.tokens.output} tokens`}
                  size="small"
                  variant="outlined"
                />
              )}
              {message.latency_ms > 0 && (
                <Chip
                  icon={<Speed />}
                  label={message.latency_ms > 1000 ? `${(message.latency_ms / 1000).toFixed(1)}s` : `${message.latency_ms}ms`}
                  size="small"
                  variant="outlined"
                />
              )}
              <Tooltip title={copied ? "Copied!" : "Copy answer"}>
                <IconButton size="small" onClick={handleCopy}>
                  <ContentCopy fontSize="small" />
                </IconButton>
              </Tooltip>
              {onBranch && (
                <Tooltip title="Branch conversation from here">
                  <IconButton size="small" onClick={onBranch}>
                    <CallSplit fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
          </Box>
        </Box>
      )}

      {/* Loading state */}
      {message.answer === null && (
        <Box sx={{ display: "flex", justifyContent: "flex-start" }}>
          <AnswerBubble>
            <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
              Thinking...
            </Typography>
          </AnswerBubble>
        </Box>
      )}
    </Box>
  );
}
