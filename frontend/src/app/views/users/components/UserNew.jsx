import { useState } from "react";
import useAuth from "app/hooks/useAuth";
import { useNavigate } from "react-router-dom";
import {
  Box,
  Button,
  Card,
  Divider,
  Grid,
  Stack,
  styled,
  Switch,
  TextField,
  Typography
} from "@mui/material";
import FormControlLabel from "@mui/material/FormControlLabel";
import { H5, Paragraph } from "app/components/Typography";
import { FlexBox } from "app/components/FlexBox";
import { toast } from "react-toastify";
import api from "app/utils/api";

const Dot = styled("div")(({ theme }) => ({
  width: 8,
  height: 8,
  flexShrink: 0,
  borderRadius: "50%",
  backgroundColor: theme.palette.primary.main
}));

export default function UserNew() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [state, setState] = useState({
    username: "",
    password: "",
    confirmPassword: "",
    is_admin: false,
    is_private: false,
    is_restricted: false
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event) => {
    event.preventDefault();

    if (!state.username.trim()) {
      toast.error("Username is required");
      return;
    }

    if (!state.password) {
      toast.error("Password is required");
      return;
    }

    if (state.password !== state.confirmPassword) {
      toast.error("Passwords do not match");
      return;
    }

    if (state.password.length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    setLoading(true);

    api.post("/users", {
      username: state.username,
      password: state.password,
      is_admin: state.is_admin,
      is_private: state.is_private,
      is_restricted: state.is_restricted
    }, auth.user.token)
      .then((response) => {
        navigate("/user/" + response.username);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({
      ...state,
      [event.target.name]: event.target.type === "checkbox" ? event.target.checked : event.target.value
    });
  };

  return (
    <Card>
      <H5 padding={3}>Create New User</H5>
      <Divider />

      <Box padding={3}>
        <form onSubmit={handleSubmit}>
          <Grid container spacing={5}>
            <Grid item sm={6} xs={12}>
              <Stack spacing={3}>
                <TextField
                  fullWidth
                  required
                  name="username"
                  variant="outlined"
                  label="Username"
                  value={state.username}
                  onChange={handleChange}
                  autoFocus
                />

                <TextField
                  fullWidth
                  required
                  type="password"
                  name="password"
                  variant="outlined"
                  label="Password"
                  value={state.password}
                  onChange={handleChange}
                />

                <TextField
                  fullWidth
                  required
                  type="password"
                  name="confirmPassword"
                  variant="outlined"
                  label="Confirm Password"
                  value={state.confirmPassword}
                  onChange={handleChange}
                  error={state.confirmPassword !== "" && state.password !== state.confirmPassword}
                  helperText={
                    state.confirmPassword !== "" && state.password !== state.confirmPassword
                      ? "Passwords do not match"
                      : ""
                  }
                />

                <FormControlLabel
                  label="Administrator"
                  control={
                    <Switch
                      checked={state.is_admin}
                      name="is_admin"
                      onChange={handleChange}
                    />
                  }
                />

                <FormControlLabel
                  label="Local AI only"
                  control={
                    <Switch
                      checked={state.is_private}
                      name="is_private"
                      onChange={handleChange}
                    />
                  }
                />

                <Box>
                  <FormControlLabel
                    label="Restricted"
                    control={
                      <Switch
                        checked={state.is_restricted}
                        name="is_restricted"
                        onChange={handleChange}
                      />
                    }
                  />
                  <Typography variant="caption" color="text.secondary" display="block">
                    Can only chat with existing projects. No create, edit, ingest, or direct access.
                  </Typography>
                </Box>
              </Stack>

              <Stack direction="row" spacing={2} mt={4}>
                <Button type="submit" variant="contained" disabled={loading}>
                  {loading ? "Creating..." : "Create User"}
                </Button>
                <Button variant="outlined" onClick={() => navigate("/users")}>
                  Cancel
                </Button>
              </Stack>
            </Grid>

            <Grid item sm={6} xs={12}>
              <H5>Password recommendations:</H5>

              <Stack spacing={1} mt={2}>
                <FlexBox alignItems="center" gap={1}>
                  <Dot />
                  <Paragraph fontSize={13}>
                    8 characters long - the more, the better
                  </Paragraph>
                </FlexBox>

                <FlexBox alignItems="center" gap={1}>
                  <Dot />
                  <Paragraph fontSize={13}>At least one lowercase character</Paragraph>
                </FlexBox>

                <FlexBox alignItems="center" gap={1}>
                  <Dot />
                  <Paragraph fontSize={13}>At least one uppercase character</Paragraph>
                </FlexBox>

                <FlexBox alignItems="center" gap={1}>
                  <Dot />
                  <Paragraph fontSize={13}>
                    At least one number, symbol, or whitespace character
                  </Paragraph>
                </FlexBox>
              </Stack>
            </Grid>
          </Grid>
        </form>
      </Box>
    </Card>
  );
}
