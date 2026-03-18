import {
  Card,
  Table,
  styled,
  Divider,
  TableRow,
  TableBody,
  TableCell,
  Button
} from "@mui/material";

import { H4, Small } from "app/components/Typography";
import { FlexBetween, FlexBox } from "app/components/FlexBox";
import QRCode from "react-qr-code";
import { Edit, Delete } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import ReactJson from '@microlink/react-json-view';
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const ContentBox = styled(FlexBox)({
  alignItems: "center",
  flexDirection: "column"
});

export default function LLMInfo({ llm, projects }) {
  const navigate = useNavigate();
  const auth = useAuth();

  const handleDeleteClick = () => {
    if (window.confirm("Are you sure you to delete the llm " + llm.name + "?")) {
      api.delete("/llms/" + llm.name, auth.user.token)
        .then(() => {
          navigate("/llms");
        }).catch(() => {});
    }
  };

  return (
    <Card sx={{ pt: 3 }} elevation={3}>
      <ContentBox mb={3} alignContent="center">
        <QRCode
          size={256}
          style={{ width: 84, height: 84 }}
          value={window.location.href || "RESTai"}
          viewBox={`0 0 256 256`}
        />

        <H4 sx={{ mt: "16px", mb: "8px" }}>{llm.name}</H4>
        <Small color="text.secondary">{llm.description}</Small>
      </ContentBox>

      <Divider />

      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Class</TableCell>
            <TableCell colSpan={4}>{llm.class_name}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Type</TableCell>
            <TableCell colSpan={4}>{llm.type}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Privacy</TableCell>
            <TableCell colSpan={4}>{llm.privacy}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Options</TableCell>
            <TableCell colSpan={4}>{llm.options && (<ReactJson src={llm.options} enableClipboard={true} name={false} />)}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Description</TableCell>
            <TableCell colSpan={4}>{llm.description}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Input Cost (per Million Tokens)</TableCell>
            <TableCell colSpan={4}>{llm.input_cost}€</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Output Cost (per Million Tokens)</TableCell>
            <TableCell colSpan={4}>{llm.output_cost}€</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Context Window</TableCell>
            <TableCell colSpan={4}>{llm.context_window || 4096} tokens</TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <FlexBetween p={2}>
        {auth.user.is_admin === true &&
          <>
            <Button variant="outlined" onClick={() => { navigate("/llm/" + llm.name + "/edit") }} startIcon={<Edit fontSize="small" />}>
              Edit
            </Button>
            <Button variant="outlined" color="error" onClick={handleDeleteClick} startIcon={<Delete fontSize="small" />}>
              Delete
            </Button>
          </>
        }
      </FlexBetween>
    </Card>
  );
}