import { useNavigate } from "react-router-dom";
import { Card, Button, styled, Avatar, Tooltip, Box } from "@mui/material";
import { Visibility, Edit, Delete } from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import sha256 from 'crypto-js/sha256';
import { useTheme } from "@mui/material/styles";
import useAuth from "app/hooks/useAuth";

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

const StyledAvatar = styled(Avatar)(() => ({
  width: "32px !important",
  height: "32px !important",
  marginRight: "10px"
}));

export default function UsersTable({ users = [], title = "Users", onDelete }) {
  const navigate = useNavigate();
  const { palette } = useTheme();
  const auth = useAuth();
  const isAdmin = auth.user?.is_admin;

  const CustomToolbar = () => (
    isAdmin && (
      <Tooltip title="Create New User">
        <StyledButton
          variant="contained"
          color="primary"
          onClick={() => navigate("/users/new")}
          sx={{ ml: 2 }}
        >
          New User
        </StyledButton>
      </Tooltip>
    )
  );

  return (
    <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
      <MUIDataTable
        title={title}
        data={users.map(user => [
          user.username,
          user.is_admin ? "Admin" : "User",
          user.sso ? "SSO" : "Local",
          user.projects?.length || 0,
          user,
        ])}
        columns={[
          {
            name: "Username",
            options: {
              customBodyRender: (value) => (
                <StyledButton onClick={() => navigate("/user/" + value)} color="primary" sx={{ textTransform: "none" }}>
                  <StyledAvatar src={`https://www.gravatar.com/avatar/${sha256(value).toString()}`} />
                  {value}
                </StyledButton>
              )
            }
          },
          {
            name: "Role",
            options: {
              customBodyRender: (value) => (
                value === "Admin" ? <Small bgcolor={palette.error.main}>Admin</Small> : <Small bgcolor={palette.primary.main}>User</Small>
              )
            }
          },
          {
            name: "Auth",
            options: {
              customBodyRender: (value) => (
                value === "SSO" ? <Small bgcolor={palette.success.main}>SSO</Small> : <Small bgcolor={palette.error.main}>Local</Small>
              )
            }
          },
          "Projects",
          {
            name: "Actions",
            options: {
              filter: false,
              sort: false,
              customBodyRender: (user) => (
                <Box display="flex" alignItems="center" gap={1}>
                  <Tooltip title="View">
                    <StyledButton onClick={() => navigate("/user/" + user.username)} color="primary" variant="outlined" sx={{ minWidth: 0, p: 1, m: 0 }}>
                      <Visibility fontSize="small" />
                    </StyledButton>
                  </Tooltip>
                  {isAdmin && (
                    <>
                      <Tooltip title="Edit">
                        <StyledButton onClick={() => navigate("/user/" + user.username)} color="secondary" variant="outlined" sx={{ minWidth: 0, p: 1, m: 0 }}>
                          <Edit fontSize="small" />
                        </StyledButton>
                      </Tooltip>
                      <Tooltip title="Delete">
                        <StyledButton onClick={() => onDelete && onDelete(user.username)} color="error" variant="outlined" sx={{ minWidth: 0, p: 1, m: 0 }}>
                          <Delete fontSize="small" />
                        </StyledButton>
                      </Tooltip>
                    </>
                  )}
                </Box>
              )
            }
          }
        ]}
        options={{
          print: false,
          selectableRows: "none",
          download: false,
          filter: true,
          viewColumns: false,
          rowsPerPage: 25,
          elevation: 0,
          textLabels: {
            body: {
              noMatch: "No users found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          },
          customToolbar: CustomToolbar
        }}
      />
    </Card>
  );
}
