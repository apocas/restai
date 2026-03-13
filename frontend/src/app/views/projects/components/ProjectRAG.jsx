import { Article } from "@mui/icons-material";
import {
  Card,
  Table,
  styled,
  Divider,
  TableRow,
  TableBody,
  TableCell,
  Switch,
  Box
} from "@mui/material";

import { H4 } from "app/components/Typography";

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

export default function ProjectRAG({ project, projects }) {
  return (
    <Card elevation={3}>
      <FlexBox>
        <Article sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>
          RAG
        </H4>
      </FlexBox>
      <Divider />

      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Documents</TableCell>
            <TableCell>{project.chunks}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Vectorstore</TableCell>
            <TableCell>{project.vectorstore}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Embeddings</TableCell>
            <TableCell>{project.embeddings}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>K</TableCell>
            <TableCell>{project.options.k}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Cutoff</TableCell>
            <TableCell>{project.options.score}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Colbert Rerank</TableCell>
            <TableCell>
              <Switch
                disabled
                checked={project.options.colbert_rerank}
                inputProps={{ "aria-label": "secondary checkbox" }}
              />
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>LLM Rerank</TableCell>
            <TableCell>
              <Switch
                disabled
                checked={project.options.llm_rerank}
                inputProps={{ "aria-label": "secondary checkbox" }}
              />
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Cache Threshold</TableCell>
            <TableCell>{project.options.cache_threshold}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Cache</TableCell>
            <TableCell>
              <Switch
                disabled
                checked={project.options.cache}
                inputProps={{ "aria-label": "secondary checkbox" }}
              />
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Card>
  );
}
