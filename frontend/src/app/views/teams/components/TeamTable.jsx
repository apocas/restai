import React from "react";
import { useTheme, Card, styled, Tooltip, IconButton, Chip, Box, Button as StyledButton } from "@mui/material";
import { Visibility, Edit, Delete } from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";

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

export default function TeamTable({ teams, onView, onEdit, onDelete, isAdmin }) {
  const { user } = useAuth();
  const { palette } = useTheme();
  const navigate = useNavigate();

  // Custom toolbar for the top right
  const CustomToolbar = () => (
    isAdmin && (
      <Tooltip title="Create New Team">
        <StyledButton
          variant="contained"
          color="primary"
          onClick={() => navigate("/teams/new")}
          sx={{ ml: 2 }}
        >
          New Team
        </StyledButton>
      </Tooltip>
    )
  );

  if (!teams || teams.length === 0) {
    return (
      <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
        <Box p={3} textAlign="center">
          No teams found. {isAdmin && "Click 'New Team' to create one."}
        </Box>
      </Card>
    );
  }

  return (
    <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
      <MUIDataTable
        title={"Teams"}
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
              noMatch: "No teams found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          },
          customToolbar: CustomToolbar
        }}
        data={teams.map(team => [
          team.name,
          team.description || "No description",
          team.users?.length || 0,
          team.projects?.length || 0,
          isAdmin ? (
            <Chip label="Platform Admin" color="primary" variant="outlined" size="small" />
          ) : team.admins?.some(admin => admin.id === user?.id) ? (
            <Chip label="Team Admin" color="secondary" variant="outlined" size="small" />
          ) : (
            <Chip label="Member" color="default" variant="outlined" size="small" />
          ),
          team
        ])}
        columns={[
          {
            name: "Name",
            options: {
              customBodyRender: (value, tableMeta) => (
                <Box display="flex" alignItems="center" gap={1}>
                  {value}
                </Box>
              )
            }
          },
          {
            name: "Description",
            options: {
              customBodyRender: value => (
                <Box sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{value}</Box>
              )
            }
          },
          {
            name: "Users",
            options: {}
          },
          {
            name: "Projects",
            options: {}
          },
          {
            name: "Your Role",
            options: {}
          },
          {
            name: "Actions",
            options: {
              customBodyRender: (team) => (
                <Box display="flex" alignItems="center" gap={1}>
                  <Tooltip title="View Team">
                    <StyledButton onClick={() => onView(team.id)} color="primary" variant="outlined" sx={{ minWidth: 0, p: 1 }}>
                      <Visibility fontSize="small" />
                    </StyledButton>
                  </Tooltip>
                  {(isAdmin || team.admins?.some(admin => admin.id === user?.id)) && (
                    <Tooltip title="Edit Team">
                      <StyledButton onClick={() => onEdit(team.id)} color="secondary" variant="outlined" sx={{ minWidth: 0, p: 1 }}>
                        <Edit fontSize="small" />
                      </StyledButton>
                    </Tooltip>
                  )}
                  {isAdmin && (
                    <Tooltip title="Delete Team">
                      <StyledButton onClick={() => onDelete(team.id)} color="error" variant="outlined" sx={{ minWidth: 0, p: 1 }}>
                        <Delete fontSize="small" />
                      </StyledButton>
                    </Tooltip>
                  )}
                </Box>
              )
            }
          }
        ]}
      />
    </Card>
  );
}