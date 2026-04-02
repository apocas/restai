import {
  Box,
  Card,
  styled,
  Button,
  Tooltip,
  useTheme
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import MUIDataTable from "mui-datatables";
import { Edit, Delete } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import api from "app/utils/api";

const StyledButton = styled(Button)(({ theme }) => ({
  margin: theme.spacing(1)
}));

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

export default function EmbeddingsTable({ embeddings = [], title = "Embeddings" }) {
  const auth = useAuth();
  const { palette } = useTheme();
  const navigate = useNavigate();

  const handleDeleteClick = (embedding) => {
    if (window.confirm(`Are you sure you want to delete '${embedding.name}'?`)) {
      api.delete("/embeddings/" + embedding.id, auth.user.token)
        .then(() => {
          toast.success(`Successfully deleted ${embedding.name}`);
          window.location.reload();
        }).catch(() => {});
    }
  };

  const isAdmin = auth.user?.is_admin;

  const CustomToolbar = () => (
    isAdmin ? (
      <Tooltip title="Create New Embedding">
        <StyledButton
          variant="contained"
          color="primary"
          onClick={() => navigate("/embeddings/new")}
          sx={{ ml: 2 }}
        >
          New Embedding
        </StyledButton>
      </Tooltip>
    ) : null
  );

  return (
    <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
      <MUIDataTable
        title={title}
        options={{
          print: false,
          selectableRows: "none",
          download: false,
          filter: true,
          viewColumns: false,
          rowsPerPage: 10,
          rowsPerPageOptions: [10, 15, 100],
          elevation: 0,
          textLabels: {
            body: {
              noMatch: "No embeddings found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          },
          customToolbar: CustomToolbar
        }}
        data={embeddings.map(emb => [emb.name, emb.class_name, emb.privacy, emb.dimension, emb])}
        columns={[
          {
            name: "Name",
            options: {
              customBodyRender: (value, tableMeta) => {
                const emb = tableMeta.rowData[4];
                return (
                  <StyledButton onClick={() => navigate("/embedding/" + emb.id)} color="primary">{value}</StyledButton>
                );
              }
            }
          },
          {
            name: "Class",
            options: {}
          },
          {
            name: "Privacy",
            options: {
              customBodyRender: (value) => (
                value === "private" ? (
                  <Small bgcolor={palette.success.main}>{value}</Small>
                ) : (
                  <Small bgcolor={palette.error.main}>{value}</Small>
                )
              )
            }
          },
          {
            name: "Dimension",
            options: {}
          },
          ...(isAdmin ? [{
            name: "Actions",
            options: {
              filter: false,
              sort: false,
              customBodyRender: (emb) => (
                <Box display="flex" alignItems="center" gap={1}>
                  <Tooltip title="Edit">
                    <StyledButton onClick={() => navigate("/embedding/" + emb.id + "/edit")} color="secondary" variant="outlined" sx={{ minWidth: 0, p: 1 }}>
                      <Edit fontSize="small" />
                    </StyledButton>
                  </Tooltip>
                  <Tooltip title="Delete">
                    <StyledButton onClick={() => handleDeleteClick(emb)} color="error" variant="outlined" sx={{ minWidth: 0, p: 1 }}>
                      <Delete fontSize="small" />
                    </StyledButton>
                  </Tooltip>
                </Box>
              )
            }
          }] : [])
        ]}
      />
    </Card>
  );
}
