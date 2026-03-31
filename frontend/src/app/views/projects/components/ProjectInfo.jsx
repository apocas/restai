import { useState, useEffect } from "react";
import {
  Card,
  Chip,
  Table,
  styled,
  Divider,
  TableRow,
  TableBody,
  TableCell,
  Switch,
  Button,
  Tooltip,
  Avatar,
  Box,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
} from "@mui/material";

import { H4, Small } from "app/components/Typography";
import { FlexBetween, FlexBox } from "app/components/FlexBox";
import { Edit } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { SportsEsports, Delete, Code, Article, ViewInAr, Science, ClearAll, Security, ContentCopy } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import sha256 from 'crypto-js/sha256';
import BAvatar from "boring-avatars";
import api from "app/utils/api";

const ContentBox = styled(FlexBox)({
  alignItems: "center",
  flexDirection: "column"
});

const StyledAvatar = styled(Avatar)(() => ({
  width: "32px !important",
  height: "32px !important"
}));

export default function ProjectInfo({ project, projects }) {
  const navigate = useNavigate();
  const auth = useAuth();
  const [cloneOpen, setCloneOpen] = useState(false);
  const [cloneName, setCloneName] = useState("");
  const [health, setHealth] = useState(null);

  useEffect(() => {
    if (project.id) {
      api.get("/projects/health", auth.user.token, { silent: true })
        .then((data) => {
          const h = (data || []).find((x) => x.project_id === project.id);
          if (h) setHealth(h);
        })
        .catch(() => {});
    }
  }, [project.id]);

  const handleClone = () => {
    if (!cloneName.trim()) return;
    api.post("/projects/" + project.id + "/clone", { name: cloneName.trim() }, auth.user.token)
      .then((response) => {
        setCloneOpen(false);
        setCloneName("");
        navigate("/project/" + response.project);
      })
      .catch(() => {});
  };

  const handleDeleteClick = () => {
    if (window.confirm("Are you sure you to delete the project " + project.name + "?")) {
      api.delete("/projects/" + project.id, auth.user.token)
        .then(() => {
          navigate("/projects");
        }).catch(() => {});
    }
  };

  return (
    <Card sx={{ pt: 3 }} elevation={3}>
      <ContentBox mb={3} alignContent="center">
        <BAvatar name={project.name} size={84} variant="pixel" colors={["#73c5aa", "#c6c085", "#f9a177", "#f76157", "#4c1b05"]}/>

        <H4 sx={{ mt: "16px", mb: "8px" }}>{project.name}</H4>
        <Small color="text.secondary">{project.type}</Small>
        {health && (
          <Tooltip
            title={
              <Box>
                <div><strong>Health: {health.health}/100</strong></div>
                <div>Requests (7d): {health.requests_7d || 0}</div>
                <div>Avg Latency: {health.avg_latency ? health.avg_latency + "ms" : "N/A"}</div>
                <div>Guard Block Rate: {health.guard_block_rate !== null ? (health.guard_block_rate * 100).toFixed(1) + "%" : "N/A"}</div>
                <div>Eval Score: {health.eval_score !== null ? (health.eval_score * 100).toFixed(0) + "%" : "N/A"}</div>
              </Box>
            }
            placement="bottom"
          >
            <Chip
              label={`Health: ${health.health}`}
              size="small"
              color={health.health >= 70 ? "success" : health.health >= 40 ? "warning" : "error"}
              sx={{ mt: 1, fontWeight: "bold", cursor: "default" }}
            />
          </Tooltip>
        )}
      </ContentBox>

      <Divider />

      <Table>
        <TableBody>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Name</TableCell>
            <TableCell>{project.human_name}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>ID</TableCell>
            <TableCell>{project.id}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Description</TableCell>
            <TableCell>{project.human_description}</TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Shared</TableCell>
            <TableCell>
              <Switch
                disabled
                checked={project.public ?? false}
                inputProps={{ "aria-label": "secondary checkbox" }}
              />
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Telegram</TableCell>
            <TableCell>
              <Switch
                disabled
                checked={!!project.options?.telegram_token}
                inputProps={{ "aria-label": "telegram status" }}
              />
            </TableCell>
          </TableRow>
          <TableRow>
            <TableCell sx={{ pl: 2 }}>Users</TableCell>
            <TableCell>
              <Box display="flex" alignItems="center" gap={1}>
                {(project.users || []).map((user, index) => (
                  <div key={user || index}>
                    <Tooltip title={user} placement="top">
                      <StyledAvatar src={"https://www.gravatar.com/avatar/" + sha256(user)} />
                    </Tooltip>
                  </div>
                ))}
                {(project.users || []).length >= 3 &&
                  <div>
                    <Tooltip title={project.users.slice(2).map(user => user).join(", ")} placement="top">
                      <StyledAvatar sx={{ fontSize: "14px" }}>+{project.users.length - 2}</StyledAvatar>
                    </Tooltip>
                  </div>
                }
              </Box>
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>

      <FlexBetween p={2}>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/edit") }} startIcon={<Edit fontSize="small" />}>
          Edit
        </Button>
        {project.type === "block" && (
          <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/ide") }} startIcon={<ViewInAr fontSize="small" />}>
            IDE
          </Button>
        )}
        <Button variant="outlined" onClick={() => { setCloneName(project.name + "-copy"); setCloneOpen(true); }} startIcon={<ContentCopy fontSize="small" />}>
          Clone
        </Button>
        <Button variant="outlined" color="error" onClick={handleDeleteClick} startIcon={<Delete fontSize="small" />}>
          Delete
        </Button>
      </FlexBetween>
      <FlexBetween p={2} pt={0}>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/api") }} startIcon={<Code fontSize="small" />}>
          API
        </Button>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/playground") }} startIcon={<SportsEsports fontSize="small" />}>
          Playground
        </Button>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/evals") }} startIcon={<Science fontSize="small" />}>
          Evals
        </Button>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/guards") }} startIcon={<Security fontSize="small" />}>
          Guards
        </Button>
        <Button variant="outlined" onClick={() => { navigate("/project/" + project.id + "/logs") }} startIcon={<Article fontSize="small" />}>
          Logs
        </Button>
      </FlexBetween>
      {project.options?.cache && (
        <FlexBetween p={2} pt={0}>
          <Button
            variant="outlined"
            color="warning"
            startIcon={<ClearAll fontSize="small" />}
            onClick={() => {
              api.delete("/projects/" + project.id + "/cache", auth.user.token)
                .then(() => {})
                .catch(() => {});
            }}
          >
            Clear Cache
          </Button>
        </FlexBetween>
      )}

      {/* Clone dialog */}
      <Dialog open={cloneOpen} onClose={() => setCloneOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Clone Project</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus fullWidth margin="dense"
            label="New project name"
            value={cloneName}
            onChange={(e) => setCloneName(e.target.value)}
            helperText="Settings, eval datasets, and prompt versions will be cloned. Logs and documents will not."
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCloneOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleClone} disabled={!cloneName.trim()}>Clone</Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}