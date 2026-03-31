import { useState, useEffect } from "react";
import {
  Box, Card, Chip, Divider, Grid, styled, Typography,
  Table, TableBody, TableCell, TableHead, TableRow,
  TextField, MenuItem, Button, IconButton,
} from "@mui/material";
import { History, ChevronLeft, ChevronRight } from "@mui/icons-material";
import Breadcrumb from "app/components/Breadcrumb";
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const FlexBox = styled(Box)({ display: "flex", alignItems: "center" });

const ACTION_COLORS = {
  POST: "success",
  PATCH: "info",
  PUT: "info",
  DELETE: "error",
};

export default function AuditLog() {
  const auth = useAuth();
  const [entries, setEntries] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [filterUsername, setFilterUsername] = useState("");
  const [filterAction, setFilterAction] = useState("");
  const pageSize = 25;

  const fetchEntries = () => {
    const params = new URLSearchParams({
      start: page * pageSize,
      end: (page + 1) * pageSize,
    });
    if (filterUsername) params.set("username", filterUsername);
    if (filterAction) params.set("action", filterAction);

    api.get("/audit?" + params.toString(), auth.user.token, { silent: true })
      .then((data) => {
        setEntries(data.entries || []);
        setTotal(data.total || 0);
      })
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Audit Log";
    fetchEntries();
  }, [page, filterUsername, filterAction]);

  const totalPages = Math.ceil(total / pageSize);

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Audit Log", path: "/audit" }]} />
      </Box>

      <ContentBox>
        <Card elevation={3}>
          <FlexBox justifyContent="space-between" sx={{ pr: 2 }}>
            <FlexBox>
              <History sx={{ ml: 2 }} />
              <H4 sx={{ p: 2 }}>Audit Log</H4>
              <Typography variant="caption" color="text.secondary">
                {total} entries
              </Typography>
            </FlexBox>
            <FlexBox sx={{ gap: 1 }}>
              <TextField
                size="small"
                label="Username"
                value={filterUsername}
                onChange={(e) => { setFilterUsername(e.target.value); setPage(0); }}
                sx={{ width: 150 }}
              />
              <TextField
                select
                size="small"
                label="Action"
                value={filterAction}
                onChange={(e) => { setFilterAction(e.target.value); setPage(0); }}
                sx={{ width: 120 }}
              >
                <MenuItem value="">All</MenuItem>
                <MenuItem value="POST">POST</MenuItem>
                <MenuItem value="PATCH">PATCH</MenuItem>
                <MenuItem value="DELETE">DELETE</MenuItem>
              </TextField>
            </FlexBox>
          </FlexBox>
          <Divider />

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell sx={{ pl: 2 }}>Date</TableCell>
                <TableCell>User</TableCell>
                <TableCell>Action</TableCell>
                <TableCell>Resource</TableCell>
                <TableCell align="center" sx={{ pr: 2 }}>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {entries.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5} align="center" sx={{ py: 4 }}>
                    <Typography variant="body2" color="text.secondary">No audit entries found</Typography>
                  </TableCell>
                </TableRow>
              ) : (
                entries.map((e) => (
                  <TableRow key={e.id}>
                    <TableCell sx={{ pl: 2, whiteSpace: "nowrap" }}>
                      {e.date ? new Date(e.date).toLocaleString() : ""}
                    </TableCell>
                    <TableCell>{e.username || "—"}</TableCell>
                    <TableCell>
                      <Chip
                        label={e.action}
                        size="small"
                        color={ACTION_COLORS[e.action] || "default"}
                        variant="outlined"
                      />
                    </TableCell>
                    <TableCell sx={{ maxWidth: 350, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      <code>{e.resource}</code>
                    </TableCell>
                    <TableCell align="center" sx={{ pr: 2 }}>
                      <Chip
                        label={e.status_code}
                        size="small"
                        color={e.status_code < 400 ? "success" : "error"}
                        variant="outlined"
                      />
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>

          {/* Pagination */}
          {totalPages > 1 && (
            <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", p: 2, gap: 1 }}>
              <IconButton onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0} size="small">
                <ChevronLeft />
              </IconButton>
              <Typography variant="body2">
                Page {page + 1} of {totalPages}
              </Typography>
              <IconButton onClick={() => setPage(Math.min(totalPages - 1, page + 1))} disabled={page >= totalPages - 1} size="small">
                <ChevronRight />
              </IconButton>
            </Box>
          )}
        </Card>
      </ContentBox>
    </Container>
  );
}
