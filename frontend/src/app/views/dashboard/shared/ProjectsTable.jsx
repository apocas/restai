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
import BAvatar from "boring-avatars";

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


export default function ProjectsTable({ projects = [], title = "Projects", compact = false }) {
  const { palette } = useTheme();
  const bgError = palette.error.main;
  const bgSecondary = palette.secondary.main;
  const navigate = useNavigate();

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
    <Card elevation={0} sx={{ pt: "20px", borderRadius: 3, border: "1px solid", borderColor: "divider" }}>
      <MUIDataTable
        title={title}
        options={{
          "print": false,
          "selectableRows": "none",
          "download": false,
          "filter": !compact,
          "search": !compact,
          "pagination": !compact,
          "viewColumns": false,
          ...(compact ? {} : { "rowsPerPage": 10, "rowsPerPageOptions": [10, 15, 100] }),
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
        data={projects.map(project => ["", project.id, project.name, project.type, project.llm, JSON.stringify(project.users || []), project.team ? project.team.name : "", project.id])}
        columns={[{
          name: "",
          options: {
            customBodyRender: (value, tableMeta) => (
              <Box display="flex" alignItems="center" gap={4} ml={2}>
                <BAvatar name={tableMeta.rowData[2]} size={32} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]} />
              </Box>
            ),
            setCellHeaderProps: () => ({ style: { width: '60px' } }),
            setCellProps: () => ({ style: { width: '60px' } }),
          }
        }, {
          name: "ID",
          options: { display: false }
        }, {
          name: "Name",
          options: {
            customBodyRender: (value, tableMeta) => (
              <Box display="flex" alignItems="center" gap={4}>
                <StyledButton onClick={() => { navigate("/project/" + tableMeta.rowData[1]) }} color="primary">{value}</StyledButton>
              </Box>
            )
          }
        }, {
          name: "Type",
          options: {
            customBodyRender: (value) => (
              <div>{value === "rag" ? (
                <Small bgcolor={bgSecondary}>{value}</Small>
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
            customBodyRender: (value) => {
              let users = [];
              try { users = typeof value === "string" ? JSON.parse(value) : Array.isArray(value) ? value : []; } catch(e) {}
              return (
              <div>
                <Box display="flex" alignItems="center" gap={1}>
                  {users.slice(0, 1).map((user, index) => (
                    <div key={user.id || user.username || index}>
                      <Tooltip title={user.username} placement="top">
                        <StyledAvatar src={"https://www.gravatar.com/avatar/" + sha256(user.username)} />
                      </Tooltip>
                    </div>
                  ))}
                  {users.length >= 2 &&
                    <div>
                      <Tooltip title={users.slice(1).map(user => user.username).join(", ")} placement="top">
                        <StyledAvatar sx={{ fontSize: "14px" }}>+{users.length - 1}</StyledAvatar>
                      </Tooltip>
                    </div>
                  }
                </Box>
              </div>
            );
            }
          }
        },
        {
          name: "Team",
          options: {
            customBodyRender: (value) => (
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
            customBodyRender: (value) => (
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
    </Card>
  );
}
