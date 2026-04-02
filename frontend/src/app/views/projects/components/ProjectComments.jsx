import { useState, useEffect } from "react";
import {
  Avatar, Box, Button, Card, Divider, Grid, IconButton, TextField,
  Tooltip, Typography, styled,
} from "@mui/material";
import { Edit, Delete, Send, Close, Check } from "@mui/icons-material";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import sha256 from "crypto-js/sha256";

const SectionTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  fontSize: "0.9rem",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.5),
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1),
}));

const CommentCard = styled(Box)(({ theme }) => ({
  display: "flex",
  gap: theme.spacing(1.5),
  padding: theme.spacing(2),
  borderBottom: `1px solid ${theme.palette.divider}`,
  "&:last-child": { borderBottom: "none" },
}));

export default function ProjectComments({ project }) {
  const auth = useAuth();
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editContent, setEditContent] = useState("");
  const [posting, setPosting] = useState(false);

  const fetchComments = () => {
    if (!project.id) return;
    api.get(`/projects/${project.id}/comments`, auth.user.token, { silent: true })
      .then(setComments)
      .catch(() => setComments([]));
  };

  useEffect(() => { fetchComments(); }, [project.id]);

  const handlePost = () => {
    if (!newComment.trim()) return;
    setPosting(true);
    api.post(`/projects/${project.id}/comments`, { content: newComment.trim() }, auth.user.token)
      .then(() => {
        setNewComment("");
        fetchComments();
      })
      .catch(() => {})
      .finally(() => setPosting(false));
  };

  const handleUpdate = (commentId) => {
    if (!editContent.trim()) return;
    api.patch(`/projects/${project.id}/comments/${commentId}`, { content: editContent.trim() }, auth.user.token)
      .then(() => {
        setEditingId(null);
        setEditContent("");
        fetchComments();
      })
      .catch(() => {});
  };

  const handleDelete = (commentId) => {
    api.delete(`/projects/${project.id}/comments/${commentId}`, auth.user.token)
      .then(fetchComments)
      .catch(() => {});
  };

  const startEdit = (comment) => {
    setEditingId(comment.id);
    setEditContent(comment.content);
  };

  const canModify = (comment) => {
    return auth.user?.is_admin || auth.user?.username === comment.username;
  };

  return (
    <Grid container spacing={3}>
      {/* Post new comment */}
      <Grid item xs={12}>
        <Card elevation={1} sx={{ p: 2.5 }}>
          <Box sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
            <Avatar
              src={"https://www.gravatar.com/avatar/" + sha256(auth.user?.username || "")}
              sx={{ width: 36, height: 36, mt: 0.5 }}
            />
            <TextField
              fullWidth
              multiline
              minRows={2}
              maxRows={6}
              size="small"
              placeholder="Leave a note about this project..."
              value={newComment}
              onChange={(e) => setNewComment(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) handlePost();
              }}
            />
            <Button
              variant="contained"
              size="small"
              disabled={!newComment.trim() || posting}
              onClick={handlePost}
              sx={{ minWidth: 40, px: 1, mt: 0.5 }}
            >
              <Send fontSize="small" />
            </Button>
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, ml: 6.5, display: "block" }}>
            Ctrl+Enter to post
          </Typography>
        </Card>
      </Grid>

      {/* Comments list */}
      <Grid item xs={12}>
        {comments.length > 0 ? (
          <Card elevation={1}>
            {comments.map((comment) => (
              <CommentCard key={comment.id}>
                <Tooltip title={comment.username}>
                  <Avatar
                    src={"https://www.gravatar.com/avatar/" + sha256(comment.username || "")}
                    sx={{ width: 32, height: 32, mt: 0.3 }}
                  />
                </Tooltip>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.3 }}>
                    <Typography variant="subtitle2">{comment.username}</Typography>
                    <Typography variant="caption" color="text.secondary">
                      {new Date(comment.created_at).toLocaleString()}
                      {comment.updated_at !== comment.created_at && " (edited)"}
                    </Typography>
                    <Box sx={{ flex: 1 }} />
                    {canModify(comment) && editingId !== comment.id && (
                      <>
                        <IconButton size="small" onClick={() => startEdit(comment)}>
                          <Edit sx={{ fontSize: 16 }} />
                        </IconButton>
                        <IconButton size="small" color="error" onClick={() => handleDelete(comment.id)}>
                          <Delete sx={{ fontSize: 16 }} />
                        </IconButton>
                      </>
                    )}
                  </Box>
                  {editingId === comment.id ? (
                    <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
                      <TextField
                        fullWidth
                        multiline
                        minRows={2}
                        size="small"
                        value={editContent}
                        onChange={(e) => setEditContent(e.target.value)}
                        autoFocus
                      />
                      <IconButton size="small" color="primary" onClick={() => handleUpdate(comment.id)}>
                        <Check />
                      </IconButton>
                      <IconButton size="small" onClick={() => setEditingId(null)}>
                        <Close />
                      </IconButton>
                    </Box>
                  ) : (
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                      {comment.content}
                    </Typography>
                  )}
                </Box>
              </CommentCard>
            ))}
          </Card>
        ) : (
          <Typography variant="body2" color="text.secondary" sx={{ textAlign: "center", py: 3 }}>
            No comments yet. Be the first to leave a note.
          </Typography>
        )}
      </Grid>
    </Grid>
  );
}
