import { useState, useEffect } from "react";
import {
  Box,
  Card,
  Button,
  Divider,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Typography,
  InputAdornment,
} from "@mui/material";
import { Delete, ContentCopy } from "@mui/icons-material";

import { FlexBetween } from "app/components/FlexBox";
import { H5 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { toast } from 'react-toastify';
import api from "app/utils/api";

export default function ApiKeys({ user }) {
  const auth = useAuth();
  const [keys, setKeys] = useState([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [newKey, setNewKey] = useState(null);

  const fetchKeys = () => {
    api.get("/users/" + user.username + "/apikeys", auth.user.token)
      .then((data) => setKeys(data))
      .catch(() => {});
  };

  useEffect(() => {
    if (user.username) fetchKeys();
  }, [user.username]);

  const handleCreate = () => {
    api.post("/users/" + user.username + "/apikeys", { description }, auth.user.token)
      .then((data) => {
        setNewKey(data.api_key);
        setCreateOpen(false);
        setDescription("");
        fetchKeys();
      })
      .catch(() => {});
  };

  const handleDelete = (keyId) => {
    if (!window.confirm("Are you sure you want to delete this API key?")) return;
    api.delete("/users/" + user.username + "/apikeys/" + keyId, auth.user.token)
      .then(() => {
        fetchKeys();
      })
      .catch(() => {});
  };

  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  return (
    <>
      <Card>
        <FlexBetween px={3} py={2}>
          <H5>API Keys</H5>
          <Button variant="contained" onClick={() => setCreateOpen(true)}>
            Create new key
          </Button>
        </FlexBetween>

        <Divider />

        <TableContainer sx={{ p: 3 }}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>Description</TableCell>
                <TableCell>Key Prefix</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {keys.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} align="center">
                    No API keys yet
                  </TableCell>
                </TableRow>
              ) : (
                keys.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell>{k.description || "-"}</TableCell>
                    <TableCell><code>{k.key_prefix}...</code></TableCell>
                    <TableCell>{new Date(k.created_at).toLocaleDateString()}</TableCell>
                    <TableCell align="right">
                      <Tooltip title="Delete">
                        <IconButton onClick={() => handleDelete(k.id)}>
                          <Delete color="error" />
                        </IconButton>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Card>

      {/* Create dialog */}
      <Dialog open={createOpen} onClose={() => setCreateOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Create API Key</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            margin="dense"
            label="Description (optional)"
            fullWidth
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleCreate}>Create</Button>
        </DialogActions>
      </Dialog>

      {/* Show new key dialog */}
      <Dialog open={!!newKey} onClose={() => setNewKey(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Save Your API Key</DialogTitle>
        <DialogContent>
          <Typography color="warning.main" sx={{ mb: 2 }}>
            This is the only time the full key will be shown. Copy it now.
          </Typography>
          <TextField
            fullWidth
            value={newKey || ""}
            InputProps={{
              readOnly: true,
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => copyToClipboard(newKey)}>
                    <ContentCopy />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
        </DialogContent>
        <DialogActions>
          <Button variant="contained" onClick={() => setNewKey(null)}>Done</Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
