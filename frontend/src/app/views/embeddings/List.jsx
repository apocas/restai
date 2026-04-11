import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, styled } from "@mui/material";
import { Add, Edit, Delete, Visibility, Hub } from "@mui/icons-material";
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

export default function Embeddings() {
  const [embeddings, setEmbeddings] = useState([]);
  const auth = useAuth();
  const navigate = useNavigate();
  const isAdmin = auth.user?.is_admin;

  const fetchEmbeddings = () => {
    api.get("/embeddings", auth.user.token)
      .then((d) => setEmbeddings(Array.isArray(d) ? d : (d?.embeddings || [])))
      .catch(() => {});
  };

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Embeddings";
    fetchEmbeddings();
  }, []);

  const handleDelete = (e, em) => {
    e.stopPropagation();
    if (!window.confirm(`Delete embedding "${em.name}"?`)) return;
    api.delete("/embeddings/" + em.id, auth.user.token)
      .then(() => {
        toast.success(`Deleted ${em.name}`);
        fetchEmbeddings();
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
              background: (t) => t.palette.mode === "dark" ? "rgba(249,115,22,0.15)" : "rgba(249,115,22,0.1)",
            }}
          >
            <Hub sx={{ fontSize: 18, color: "#f97316" }} />
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
    {
      key: "dimension",
      label: "Dimensions",
      sortable: true,
      align: "right",
      render: (row) => row.dimension ?? "—",
    },
  ];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: "Embeddings", path: "/embeddings" }]} />
      </Box>

      <DataList
        title="Embeddings"
        subtitle="Embedding models for RAG knowledge retrieval"
        data={embeddings}
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
        onRowClick={(row) => navigate(`/embedding/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          isAdmin && (
            <Button variant="contained" startIcon={<Add />} onClick={() => navigate("/embeddings/new")}>
              New Embedding
            </Button>
          )
        }
        actions={(row) => (
          <>
            <Tooltip title="View">
              <IconButton size="small" onClick={() => navigate(`/embedding/${row.id}`)}>
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {isAdmin && (
              <>
                <Tooltip title="Edit">
                  <IconButton size="small" onClick={() => navigate(`/embedding/${row.id}/edit`)}>
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
        emptyMessage="No embeddings configured."
      />
    </Container>
  );
}
