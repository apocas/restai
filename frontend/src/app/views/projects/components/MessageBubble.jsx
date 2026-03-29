import { useState } from "react";
import {
  Box, Chip, Collapse, IconButton, Typography, styled, Tooltip,
  Accordion, AccordionSummary, AccordionDetails,
} from "@mui/material";
import { ContentCopy, ExpandMore, Shield, Cached, Speed, TerminalOutlined } from "@mui/icons-material";
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
  whiteSpace: "pre-wrap",
}));

export default function MessageBubble({ message }) {
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
                {message.answer}
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
