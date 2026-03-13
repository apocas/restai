import { Psychology } from "@mui/icons-material";
import {
  Card,
  Table,
  styled,
  Divider,
  TableRow,
  TableBody,
  TableCell,
  Box
} from "@mui/material";

import { H4 } from "app/components/Typography";

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

export default function ProjectAI({ project, projects }) {
  return (
    <Card elevation={3}>
      <FlexBox>
        <Psychology sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>
          AI
        </H4>
      </FlexBox>
      <Divider />

      <Table>
        <TableBody>
            <TableRow>
              <TableCell sx={{ pl: 2 }}>LLM</TableCell>
              <TableCell colSpan={4}>{project.llm}</TableCell>
            </TableRow>
            {(project.type === "rag" || project.type === "inference" || project.type === "ragsql" || project.type === "agent") && (
            <TableRow>
              <TableCell sx={{ pl: 2 }}>System Message</TableCell>
              <TableCell colSpan={4}>{project.system}</TableCell>
            </TableRow>
            )}
            <TableRow>
              <TableCell sx={{ pl: 2 }}>Default Prompt</TableCell>
              <TableCell colSpan={4}>{project.default_prompt}</TableCell>
            </TableRow>
        </TableBody>
      </Table>
    </Card>
  );
}
