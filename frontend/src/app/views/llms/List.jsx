import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, styled } from "@mui/material";
import { Add, Edit, Delete, Visibility, Psychology } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import DataList from "app/components/DataList";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function LLMs() {
  const [llms, setLlms] = useState([]);
  const auth = useAuth();
  const navigate = useNavigate();
  const isAdmin = auth.user?.is_admin;

  const fetchLlms = () => {
    api.get("/llms", auth.user.token)
      .then((d) => setLlms(Array.isArray(d) ? d : (d?.llms || [])))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - LLMs";
    fetchLlms();
  }, []);

  const handleDelete = (e, llm) => {
    e.stopPropagation();
    if (!window.confirm(`Delete LLM "${llm.name}"?`)) return;
    api.delete("/llms/" + llm.id, auth.user.token)
      .then(() => {
        toast.success(`Deleted ${llm.name}`);
        fetchLlms();
      })
      .catch(() => {});
  };

  const columns = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      render: (row) => (
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5 }}>
          <Box
            sx={{
              width: 32, height: 32, borderRadius: "8px",
              display: "flex", alignItems: "center", justifyContent: "center",
              background: (t) => t.palette.mode === "dark" ? "rgba(16,185,129,0.15)" : "rgba(16,185,129,0.1)",
            }}
          >
            <Psychology sx={{ fontSize: 18, color: "#10b981" }} />
          </Box>
          <Box sx={{ fontWeight: 500 }}>{row.name}</Box>
        </Box>
      ),
    },
    {
      key: "class_name",
      label: "Class",
      sortable: true,
      render: (row) => (
        <Box sx={{ fontFamily: "monospace", fontSize: "0.85rem", color: "text.secondary" }}>
          {row.class_name}
        </Box>
      ),
    },
    {
      key: "context_window",
      label: "Context",
      sortable: true,
      render: (row) => {
        if (!row.context_window) return "—";
        if (row.context_window >= 1000) return `${Math.round(row.context_window / 1000)}K`;
        return row.context_window;
      },
    },
    {
      key: "privacy",
      label: "Privacy",
      sortable: true,
      render: (row) => (
        <Chip
          label={row.privacy}
          size="small"
          sx={{
            backgroundColor: row.privacy === "private" ? "rgba(239,68,68,0.12)" : "rgba(16,185,129,0.12)",
            color: row.privacy === "private" ? "#ef4444" : "#10b981",
            fontWeight: 600,
            fontSize: "0.72rem",
            textTransform: "uppercase",
            height: 22,
          }}
        />
      ),
    },
  ];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "LLMs", path: "/llms" }]} />
      </Box>

      <DataList
        title="LLMs"
        subtitle="Configured language models available to projects"
        data={llms}
        columns={columns}
        searchKeys={["name", "class_name"]}
        filters={[
          {
            key: "privacy",
            label: "Privacy",
            options: [
              { value: "private", label: "Private" },
              { value: "public", label: "Public" },
            ],
          },
        ]}
        onRowClick={(row) => navigate(`/llm/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          isAdmin && (
            <Button variant="contained" startIcon={<Add />} onClick={() => navigate("/llms/new")}>
              New LLM
            </Button>
          )
        }
        actions={(row) => (
          <>
            <Tooltip title="View">
              <IconButton size="small" onClick={() => navigate(`/llm/${row.id}`)}>
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {isAdmin && (
              <>
                <Tooltip title="Edit">
                  <IconButton size="small" onClick={() => navigate(`/llm/${row.id}/edit`)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title="Delete">
                  <IconButton size="small" color="error" onClick={(e) => handleDelete(e, row)}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </>
        )}
        emptyMessage="No LLMs configured."
      />
    </Container>
  );
}
