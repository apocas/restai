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
import { useTranslation } from "react-i18next";
import api from "app/utils/api";

const ContentBox = styled(FlexBox)({
  alignItems: "center",
  flexDirection: "column"
});

export default function LLMInfo({ llm, projects }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const auth = useAuth();

  const handleDeleteClick = () => {
    if (window.confirm(t("llms.info.confirmDelete", { name: llm.name }))) {
      api.delete("/llms/" + llm.id, auth.user.token)
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
            <TableCell sx={{ pl: 2 }}>{t("llms.info.class")}</TableCell>
            <TableCell colSpan={4}>{llm.class_name}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>{t("llms.info.privacy")}</TableCell>
            <TableCell colSpan={4}>{llm.privacy}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>{t("llms.info.options")}</TableCell>
            <TableCell colSpan={4}>{llm.options && (<ReactJson src={llm.options} enableClipboard={true} name={false} />)}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>{t("llms.info.description")}</TableCell>
            <TableCell colSpan={4}>{llm.description}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>{t("llms.info.inputCost")}</TableCell>
            <TableCell colSpan={4}>{llm.input_cost}€</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>{t("llms.info.outputCost")}</TableCell>
            <TableCell colSpan={4}>{llm.output_cost}€</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>{t("llms.info.contextWindow")}</TableCell>
            <TableCell colSpan={4}>{llm.context_window || 4096} {t("llms.info.tokens")}</TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <FlexBetween p={2}>
        {auth.user.is_admin === true &&
          <>
            <Button variant="outlined" onClick={() => { navigate("/llm/" + llm.id + "/edit") }} startIcon={<Edit fontSize="small" />}>
              {t("common.edit")}
            </Button>
            <Button variant="outlined" color="error" onClick={handleDeleteClick} startIcon={<Delete fontSize="small" />}>
              {t("common.delete")}
            </Button>
          </>
        }
      </FlexBetween>
    </Card>
  );
}