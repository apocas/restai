import { Box, styled } from "@mui/material";
import { Span } from "app/components/Typography";

const TerminalC = styled(Box)(() => ({
  backgroundColor: "#1e1e1e",
  color: "#00ff00",
  fontFamily: "'Courier New', Courier, monospace",
  padding: "10px",
  borderRadius: "5px",
  boxShadow: "0 0 10px rgba(0, 0, 0, 0.5)",
  margin: "20px auto",
  overflowY: "auto",
  width: "100%"
}));

const TerminalLine = styled(Box)(() => ({
  padding: "2px 0"
}));

const TerminalPrompt = styled(Span)(() => ({
  fontWeight: "bold"
}));

export default function Terminal({
  message,
}) {

  return (
    <TerminalC>

      {message.reasoning.steps.map((step, stepIndex) =>
        step.actions.map((action, actionIndex) => (
          <Box key={`${stepIndex}-${actionIndex}`}>
            <TerminalLine color={"gray"} textDecorationLine={"underline"}>{action.action}</TerminalLine>
            {action.action === "terminal" || action.action === "connect_ssh" ? (
              <>
                <TerminalLine>
                  <TerminalPrompt>ai@01 [~]# </TerminalPrompt>{action.input?.kwargs?.command || action.input?.command || ""}
                </TerminalLine>
                <TerminalLine marginLeft={"15px"} color={"#a8ffa8"}>
                  {action.output}
                </TerminalLine>
              </>
            ) : (
              <>
                <TerminalLine>
                  {action.input?.kwargs
                    ? JSON.stringify(action.input.kwargs)
                    : action.input ? JSON.stringify(action.input) : ""
                  }
                </TerminalLine>
                <TerminalLine marginLeft={"15px"} color={"#a8ffa8"}>
                  <Span sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>{action.output}</Span>
                </TerminalLine>
              </>
            )}
            {stepIndex < message.reasoning.steps.length - 1 && actionIndex === step.actions.length - 1 && (
              <Box sx={{ borderBottom: "1px solid #333", my: 1 }} />
            )}
          </Box>
        ))
      )}

    </TerminalC>
  );
}
