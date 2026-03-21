import {
  Card,
  Divider,
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@mui/material";
import ViewInArIcon from "@mui/icons-material/ViewInAr";
import { FlexBox } from "app/components/FlexBox";
import { H4 } from "app/components/Typography";

export default function ProjectBlock({ project }) {
  const workspace = project.options?.blockly_workspace;
  const blockCount = workspace?.blocks?.blocks?.length ?? 0;
  const variableCount = workspace?.variables?.length ?? 0;
  const hasWorkspace = !!workspace;

  return (
    <Card elevation={3}>
      <FlexBox>
        <ViewInArIcon sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>Block Configuration</H4>
      </FlexBox>
      <Divider />
      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Status</TableCell>
            <TableCell>{hasWorkspace ? "Configured" : "Not configured"}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Top-level Blocks</TableCell>
            <TableCell>{blockCount}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Variables</TableCell>
            <TableCell>{variableCount}</TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </Card>
  );
}
