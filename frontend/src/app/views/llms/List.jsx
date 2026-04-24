import { useState, useEffect } from "react";
import { Box, Button, Chip, IconButton, Tooltip, styled } from "@mui/material";
import { Add, Edit, Delete, Visibility, Psychology } from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useTranslation } from "react-i18next";
import DataList from "app/components/DataList";
import api from "app/utils/api";
import { colors } from "app/utils/themeColors";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 24 },
}));

export default function LLMs() {
  const { t } = useTranslation();
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
    if (!window.confirm(t("llms.info.deleteConfirm", { name: llm.name }))) return;
    api.delete("/llms/" + llm.id, auth.user.token)
      .then(() => {
        toast.success(t("llms.info.deleted", { name: llm.name }));
        fetchLlms();
      })
      .catch(() => {});
  };

  const formatCost = (v) => (v == null || v === 0 ? "—" : `$${Number(v).toFixed(4)}/1K`);
  const llmTooltip = (row) => (
    <Box sx={{ p: 0.5, maxWidth: 320 }}>
      <Box sx={{ fontWeight: 600, mb: 0.5 }}>{row.name}</Box>
      {row.description && (
        <Box sx={{ mb: 0.75, fontSize: "0.8rem", color: "grey.100", lineHeight: 1.4 }}>
          {row.description}
        </Box>
      )}
      <Box sx={{ fontSize: "0.75rem", lineHeight: 1.5 }}>
        <div><strong>{t("llms.tooltip.class")}:</strong> {row.class_name}</div>
        <div><strong>{t("llms.tooltip.privacy")}:</strong> {row.privacy}</div>
        {row.context_window && (
          <div><strong>{t("llms.tooltip.context")}:</strong> {row.context_window.toLocaleString()} {t("llms.tooltip.tokens")}</div>
        )}
        {(row.input_cost != null || row.output_cost != null) && (
          <div><strong>{t("llms.tooltip.cost")}:</strong> {t("llms.tooltip.costIn")} {formatCost(row.input_cost)}, {t("llms.tooltip.costOut")} {formatCost(row.output_cost)}</div>
        )}
      </Box>
    </Box>
  );

  const columns = [
    {
      key: "name",
      label: t("llms.columns.name"),
      sortable: true,
      render: (row) => (
        <Tooltip title={llmTooltip(row)} placement="right" arrow>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, cursor: "help" }}>
            <Box
              sx={{
                width: 32, height: 32, borderRadius: "8px",
                display: "flex", alignItems: "center", justifyContent: "center",
                background: (t) => t.palette.mode === "dark" ? "rgba(16,185,129,0.15)" : "rgba(16,185,129,0.1)",
              }}
            >
              <Psychology sx={{ fontSize: 18, color: colors.status.success }} />
            </Box>
            <Box sx={{ fontWeight: 500 }}>{row.name}</Box>
          </Box>
        </Tooltip>
      ),
    },
    {
      key: "class_name",
      label: t("llms.columns.class"),
      sortable: true,
      render: (row) => (
        <Box sx={{ fontFamily: "monospace", fontSize: "0.85rem", color: "text.secondary" }}>
          {row.class_name}
        </Box>
      ),
    },
    {
      key: "context_window",
      label: t("llms.columns.context"),
      sortable: true,
      render: (row) => {
        if (!row.context_window) return "—";
        if (row.context_window >= 1000) return `${Math.round(row.context_window / 1000)}K`;
        return row.context_window;
      },
    },
    {
      key: "privacy",
      label: t("llms.columns.privacy"),
      sortable: true,
      render: (row) => (
        <Chip
          label={row.privacy}
          size="small"
          sx={{
            backgroundColor: row.privacy === "private" ? "rgba(239,68,68,0.12)" : "rgba(16,185,129,0.12)",
            color: row.privacy === "private" ? colors.status.error : colors.status.success,
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
        <Breadcrumb routeSegments={[{ name: t("nav.llms"), path: "/llms" }]} />
      </Box>

      <DataList
        title={t("llms.title")}
        subtitle={t("llms.subtitle")}
        data={llms}
        columns={columns}
        searchKeys={["name", "class_name"]}
        filters={[
          {
            key: "privacy",
            label: t("llms.columns.privacy"),
            options: [
              { value: "private", label: t("common.private") },
              { value: "public", label: t("common.public") },
            ],
          },
        ]}
        onRowClick={(row) => navigate(`/llm/${row.id}`)}
        rowKey={(row) => row.id}
        defaultSort={{ key: "name", direction: "asc" }}
        headerAction={
          isAdmin && (
            <Button variant="contained" startIcon={<Add />} onClick={() => navigate("/llms/new")}>
              {t("llms.newBreadcrumb")}
            </Button>
          )
        }
        actions={(row) => (
          <>
            <Tooltip title={t("llms.actions.view")}>
              <IconButton size="small" onClick={() => navigate(`/llm/${row.id}`)}>
                <Visibility fontSize="small" />
              </IconButton>
            </Tooltip>
            {isAdmin && (
              <>
                <Tooltip title={t("llms.actions.edit")}>
                  <IconButton size="small" onClick={() => navigate(`/llm/${row.id}/edit`)}>
                    <Edit fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={t("llms.actions.delete")}>
                  <IconButton size="small" color="error" onClick={(e) => handleDelete(e, row)}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Tooltip>
              </>
            )}
          </>
        )}
        emptyState={{
          icon: Psychology,
          title: t("llms.emptyTitle"),
          message: t("llms.emptyMessage"),
          actionLabel: auth.user?.is_admin ? t("llms.new") : undefined,
          actionIcon: <Add fontSize="small" />,
          onAction: auth.user?.is_admin ? () => navigate("/llms/new") : undefined,
        }}
        emptyMessage={t("llms.noLlms")}
      />
    </Container>
  );
}
