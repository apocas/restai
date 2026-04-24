import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, styled } from "@mui/material";
import { Add, Edit, Delete, Visibility, Hub } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useTranslation } from "react-i18next";
import DataList from "app/components/DataList";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function Embeddings() {
  const { t } = useTranslation();
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
    if (!window.confirm(t("embeddings.info.deleteConfirm", { name: em.name }))) return;
    api.delete("/embeddings/" + em.id, auth.user.token)
      .then(() => {
        toast.success(t("embeddings.info.deleted", { name: em.name }));
        fetchEmbeddings();
      })
      .catch(() => {});
  };

  const embTooltip = (row) => (
    <Box sx={{ p: 0.5, maxWidth: 320 }}>
      <Box sx={{ fontWeight: 600, mb: 0.5 }}>{row.name}</Box>
      {row.description && (
        <Box sx={{ mb: 0.75, fontSize: "0.8rem", color: "grey.100", lineHeight: 1.4 }}>
          {row.description}
        </Box>
      )}
      <Box sx={{ fontSize: "0.75rem", lineHeight: 1.5 }}>
        <div><strong>{t("embeddings.tooltip.class")}:</strong> {row.class_name}</div>
        <div><strong>{t("embeddings.tooltip.privacy")}:</strong> {row.privacy}</div>
        {row.dimension && (
          <div><strong>{t("embeddings.tooltip.dimensions")}:</strong> {row.dimension}</div>
        )}
      </Box>
    </Box>
  );

  const columns = [
    {
      key: "name",
      label: t("embeddings.columns.name"),
      sortable: true,
      render: (row) => (
        <Tooltip title={embTooltip(row)} placement="right" arrow>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, cursor: "help" }}>
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
        </Tooltip>
      ),
    },
    {
      key: "class_name",
      label: t("embeddings.columns.class"),
      sortable: true,
      render: (row) => (
        <Box sx={{ fontFamily: "monospace", fontSize: "0.85rem", color: "text.secondary" }}>
          {row.class_name}
        </Box>
      ),
    },
    {
      key: "privacy",
      label: t("embeddings.columns.privacy"),
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
      label: t("embeddings.columns.dimensions"),
      sortable: true,
      align: "right",
      render: (row) => row.dimension ?? "—",
    },
  ];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[{ name: t("nav.embeddings"), path: "/embeddings" }]} />
      </Box>

      <DataList
        title={t("embeddings.title")}
        subtitle={t("embeddings.subtitle")}
        data={embeddings}
        columns={columns}
        searchKeys={["name", "class_name"]}
        filters={[
          {
            key: "privacy",
            label: t("embeddings.columns.privacy"),
            options: [
              { value: "private", label: t("common.private") },
              { value: "public", label: t("common.public") },
            ],
          },
        ]}
        onRowClick={(row) => navigate(`/embedding/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          isAdmin && (
            <Button variant="contained" startIcon={<Add />} onClick={() => navigate("/embeddings/new")}>
              {t("embeddings.newBreadcrumb")}
            </Button>
          )
        }
        actions={(row) => (
          <>
            <Tooltip title={t("embeddings.actions.view")}>
              <IconButton size="small" onClick={() => navigate(`/embedding/${row.id}`)}>
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {isAdmin && (
              <>
                <Tooltip title={t("embeddings.actions.edit")}>
                  <IconButton size="small" onClick={() => navigate(`/embedding/${row.id}/edit`)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={t("embeddings.actions.delete")}>
                  <IconButton size="small" color="error" onClick={(e) => handleDelete(e, row)}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </>
        )}
        emptyState={{
          icon: Hub,
          title: t("embeddings.emptyTitle"),
          message: t("embeddings.emptyMessage"),
          actionLabel: isAdmin ? t("embeddings.new") : undefined,
          actionIcon: <Add fontSize="small" />,
          onAction: isAdmin ? () => navigate("/embeddings/new") : undefined,
        }}
        emptyMessage={t("embeddings.noEmbeddings")}
      />
    </Container>
  );
}
