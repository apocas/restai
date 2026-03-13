import { Security } from "@mui/icons-material";
import {
  Card,
  Table,
  styled,
  Divider,
  TableRow,
  TableBody,
  TableCell,
  useTheme,
  Switch,
  Box
} from "@mui/material";

import { H4 } from "app/components/Typography";

const Small = styled("small")(({ bgcolor }) => ({
  width: 50,
  height: 15,
  color: "#fff",
  padding: "2px 8px",
  borderRadius: "4px",
  overflow: "hidden",
  background: bgcolor,
  boxShadow: "0 0 2px 0 rgba(0, 0, 0, 0.12), 0 2px 2px 0 rgba(0, 0, 0, 0.24)"
}));

const FlexBox = styled(Box)({
  display: "flex",
  alignItems: "center"
});

export default function ProjectRAG({ project, projects, info }) {
  const { palette } = useTheme();

  const checkPrivacy = () => {
    var embbeddingPrivacy = true;
    info.embeddings.forEach(function (element) {
      if (element.name === project.embeddings && element.privacy === "public")
        embbeddingPrivacy = false;
    })
    if (embbeddingPrivacy && project.llm_privacy === "private") {
      return true;
    } else {
      return false;
    }
  }

  return (
    <Card elevation={3}>
      <FlexBox>
        <Security sx={{ ml: 2 }} />
        <H4 sx={{ p: 2 }}>
          Security
        </H4>
      </FlexBox>
      <Divider />

      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Privacy</TableCell>
            <TableCell>
              {checkPrivacy() ?
                <Small bgcolor={palette.success.light}>Local</Small>
                :
                <Small bgcolor={palette.error.light}>Cloud</Small>
              }
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Prompt Guard</TableCell>
            <TableCell>{project.guard}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Censorship Message</TableCell>
            <TableCell>{project.censorship}</TableCell>
          </TableRow>
          {project.options && (
            <TableRow>
              <TableCell sx={{ pl: 2 }}>Logging</TableCell>
              <TableCell>
                <Switch
                  disabled
                  checked={project.options.logging !== undefined ? project.options.logging : false}
                  inputProps={{ "aria-label": "logging checkbox" }}
                />
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </Card>
  );
}
