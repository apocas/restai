import { SportsEsports } from "@mui/icons-material";
import {
  Box,
  Card,
  styled,
  useTheme,
  IconButton,
  Button,
  Tooltip,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import MUIDataTable from "mui-datatables";


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

const StyledButton = styled(Button)(({ theme }) => ({
  margin: theme.spacing(1)
}));


export default function ProjectsTableLibrary({ projects = [], title = "Projects Library" }) {
  const { palette } = useTheme();
  const bgError = palette.error.main;
  const bgPrimary = palette.primary.main;
  const bgSecondary = palette.secondary.main;

  const navigate = useNavigate();

  return (
    <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
      <MUIDataTable
        title={title}
        options={{
          "print": false,
          "selectableRows": "none",
          "download": false,
          "filter": true,
          "viewColumns": false,
          "rowsPerPage": 10,
          "rowsPerPageOptions": [10, 15, 100],
          "elevation": 0,
          "textLabels": {
            body: {
              noMatch: "No projects found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          }
        }}
        data={projects.map(project => [project.id, project, project.type, project, project, project.id])}
        columns={[{
          name: "ID",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        }, {
          name: "Name",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                <StyledButton onClick={() => { navigate("/project/" + tableMeta.rowData[0]) }} color="primary">{value.human_name || value.name}</StyledButton>
              </Box>
            )
          }
        }, {
          name: "Type",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>{value === "rag" ? (
                <Small bgcolor={bgSecondary}>{value}</Small>
              ) : value === "vision" ? (
                <Small bgcolor={bgPrimary}>{value}</Small>
              ) : value === "inference" ? (
                <Small bgcolor={palette.success.light}>{value}</Small>
              ) : value === "agent" ? (
                <Small bgcolor={palette.success.dark}>{value}</Small>
              ) : (
                <Small bgcolor={bgError}>{value}</Small>
              )}</div>
            )
          }
        }, {
          name: "Description",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>
                {value.human_description || ""}
              </div>
            )
          }
        }, {
          name: "Actions",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>
                <Tooltip title="Playground" placement="top">
                  <IconButton onClick={() => { navigate("/project/" + value + "/playground") }}>
                    <SportsEsports color="primary" />
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
