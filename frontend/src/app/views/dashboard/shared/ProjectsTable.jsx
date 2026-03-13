import { SportsEsports } from "@mui/icons-material";
import {
  Box,
  Card,
  Avatar,
  styled,
  useTheme,
  IconButton,
  Button,
  Tooltip,
} from "@mui/material";
import sha256 from 'crypto-js/sha256';
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

const StyledAvatar = styled(Avatar)(() => ({
  width: "32px !important",
  height: "32px !important"
}));

const StyledButton = styled(Button)(({ theme }) => ({
  margin: theme.spacing(1)
}));


export default function ProjectsTable({ projects = [], title = "Projects" }) {
  const { palette } = useTheme();
  const bgError = palette.error.main;
  const bgPrimary = palette.primary.main;
  const bgSecondary = palette.secondary.main;

  const navigate = useNavigate();

  // Custom toolbar for the top right
  const CustomToolbar = () => (
    <Tooltip title="Create New Project">
      <StyledButton
        variant="contained"
        color="primary"
        onClick={() => navigate("/projects/new")}
        sx={{ ml: 2 }}
      >
        New Project
      </StyledButton>
    </Tooltip>
  );

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
          },
          customToolbar: CustomToolbar
        }}
        data={projects.map(project => [project.id, project.name, project.type, project.llm, project.users, project.team.name, project.id])}
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
                <StyledButton onClick={() => { navigate("/project/" + tableMeta.rowData[0]) }} color="primary">{value}</StyledButton>
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
        }, "LLM", {
          name: "Users",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>
                <Box display="flex" alignItems="center" gap={1}>
                  {value.slice(0, 2).map((user, index) => (
                    <div key={user.id || user.username || index}>
                      <Tooltip title={user.username} placement="top">
                        <StyledAvatar src={"https://www.gravatar.com/avatar/" + sha256(user.username)} />
                      </Tooltip>
                    </div>
                  ))}
                  {value.length >= 3 &&
                    <div>
                      <Tooltip title={value.slice(2).map(user => user.username).join(", ")} placement="top">
                        <StyledAvatar sx={{ fontSize: "14px" }}>+{value.length - 2}</StyledAvatar>
                      </Tooltip>
                    </div>
                  }
                </Box>
              </div>
            )
          }
        },
        {
          name: "Team",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <div>
                <Box display="flex" alignItems="center" gap={1}>
                  {value}
                </Box>
              </div>
            )
          }
        },
        {
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
