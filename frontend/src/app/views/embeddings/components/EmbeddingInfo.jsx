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
import { toast } from 'react-toastify';

const ContentBox = styled(FlexBox)({
  alignItems: "center",
  flexDirection: "column"
});

export default function EmbeddingInfo({ embedding, projects }) {
  const navigate = useNavigate();
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();

  const handleDeleteClick = () => {
    if (window.confirm("Are you sure you to delete the embedding " + embedding.name + "?")) {
      fetch(url + "/embeddings/" + embedding.name, {
        method: 'DELETE',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      })
        .then(response => {
          if (!response.ok) {
            throw new Error('Error deleting embedding');
          }
          navigate("/embeddings");
        }).catch(err => {
          console.log(err.toString());
          toast.error("Error deleting embedding");
        });
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

        <H4 sx={{ mt: "16px", mb: "8px" }}>{embedding.name}</H4>
        <Small color="text.secondary">{embedding.description}</Small>
      </ContentBox>

      <Divider />

      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Class</TableCell>
            <TableCell colSpan={4}>{embedding.class_name}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Privacy</TableCell>
            <TableCell colSpan={4}>{embedding.privacy}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Options</TableCell>
            <TableCell colSpan={4}>{embedding.options && (<ReactJson src={JSON.parse(embedding.options)} enableClipboard={true} name={false} />)}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Description</TableCell>
            <TableCell colSpan={4}>{embedding.description}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Dimension</TableCell>
            <TableCell colSpan={4}>{embedding.dimension}</TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <FlexBetween p={2}>
        {auth.user.is_admin === true &&
          <>
            <Button variant="outlined" onClick={() => { navigate("/embedding/" + embedding.name + "/edit") }} startIcon={<Edit fontSize="small" />}>
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