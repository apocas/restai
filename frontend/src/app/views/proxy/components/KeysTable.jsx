import { Delete, Key } from "@mui/icons-material";
import {
  Card,
  styled,
  useTheme,
  IconButton,
  Tooltip,
  Box
} from "@mui/material";
import MUIDataTable from "mui-datatables";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';

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

export default function KeysTable({ keys = [], info, title = "API Keys" }) {
  const { palette } = useTheme();
  const bgPrimary = palette.primary.main;
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();

  const handleDeleteClick = (key_id, key_name) => {
    if (key_name === "default") {
      toast.error("Cannot delete the default key");
      return;
    }
    if (window.confirm("Are you sure you to delete the key " + key_name + "?")) {
      fetch(url + "/proxy/keys/" + key_id, {
        method: 'DELETE',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      })
        .then(response => {
          if (!response.ok) {
            throw new Error('Error deleting key');
          }
          window.location.reload();
        }).catch(err => {
          console.log(err.toString());
          toast.error("Error deleting key");
        });
    }
  };

  return (
    <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
      <MUIDataTable
        title={<FlexBox><Key sx={{ mr: 2}} />{title}</FlexBox>}
        options={{
          "print": false,
          "selectableRows": "none",
          "download": false,
          "filter": true,
          "viewColumns": false,
          "rowsPerPage": 25,
          "elevation": 0,
          "textLabels": {
            body: {
              noMatch: "No keys found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          }
        }}
        data={keys.map(key => [key.name, key.key, key.models, key.spend, key.max_budget, key.duration_budget, key.tpm, key.rpm, key.id])}
        columns={["Name", "Key",
          {
            name: "Models",
            options: {
              customBodyRender: (value, tableMeta, updateValue) => (
                <div  >
                  {value.map((model, index) => (
                    <Small
                      bgcolor={bgPrimary}
                      key={index}
                      sx={{
                        whiteSpace: 'nowrap',
                        wordBreak: 'break-word',
                      }}
                    >
                      {model}
                    </Small>
                  ))}
                </div>
              )
            }
          },
          {
            name: "Spend",
            options: {
              customBodyRender: (value, tableMeta, updateValue) => (
                <div>
                  {(value || 0).toFixed(3)} €
                </div>
              )
            }
          },
          {
            name: "Budget",
            options: {
              customBodyRender: (value, tableMeta, updateValue) => (
                <div>
                  {value || 0} €
                </div>
              )
            }
          },
          "Budget Duration",
          "TPM",
          "RPM",
          {
            name: "Actions",
            options: {
              customBodyRender: (value, tableMeta, updateValue) => (
                <div>
                  <Tooltip title="Delete" placement="top">
                    <IconButton onClick={() => handleDeleteClick(value, tableMeta.rowData[0])}>
                      <Delete color="error" />
                    </IconButton>
                  </Tooltip>
                </div>
              )
            }
          }]}
      />
    </Card >
  );
}
