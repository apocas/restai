import { Card, Box, Button, styled, useTheme } from "@mui/material";
import { useNavigate } from "react-router-dom";
import MUIDataTable from "mui-datatables";
import BAvatar from "boring-avatars";

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

const TopProjectsTable = ({ projects }) => {
  const navigate = useNavigate();
  const { palette } = useTheme();

  return (
    <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
      <MUIDataTable
        title="Top 10 Projects"
        options={{
          "print": false,
          "selectableRows": "none",
          "download": false,
          "filter": false,
          "search": false,
          "pagination": false,
          "viewColumns": false,
          "elevation": 0,
          "onRowClick": (rowData) => {
            navigate("/project/" + rowData[1]);
          },
          "textLabels": {
            body: {
              noMatch: "No projects found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          }
        }}
        data={projects.map((project, index) => [
          index + 1, 
          project.id,
          project.name, 
          project.type, 
          project.total_tokens, 
          project.total_cost
        ])}
        columns={[{
          name: "",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4} ml={2}>
                <BAvatar name={tableMeta.rowData[2]} size={32} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]}/>
              </Box>
            ),
            setCellHeaderProps: () => ({
              style: { width: '100px' }
            }),
            setCellProps: () => ({
              style: { width: '100px' }
            })
          }
        }, {
          name: "ID",
          options: {
            display: false
          }
        }, {
          name: "Name",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="left" gap={4}>
                <StyledButton onClick={() => navigate("/project/" + tableMeta.rowData[1])} color="primary">{value}</StyledButton>
              </Box>
            )
          }
        }, {
          name: "Type",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>{value === "rag" ? (
                <Small bgcolor={palette.secondary.main}>{value}</Small>
              ) : value === "vision" ? (
                <Small bgcolor={palette.primary.main}>{value}</Small>
              ) : value === "inference" ? (
                <Small bgcolor={palette.success.light}>{value}</Small>
              ) : value === "agent" ? (
                <Small bgcolor={palette.success.dark}>{value}</Small>
              ) : (
                <Small bgcolor={palette.error.main}>{value}</Small>
              )}</div>
            )
          }
        }, {
          name: "Token Count",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>{value.toLocaleString()}</div>
            )
          }
        }, {
          name: "Cost",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>{value.toFixed(3)} €</div>
            )
          }
        }]}
      />
    </Card>
  );
};

export default TopProjectsTable;