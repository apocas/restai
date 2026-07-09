import { useState, useEffect, useMemo } from "react";
import {
  Box, Button, Card, Chip, Grid, IconButton, InputAdornment, MenuItem,
  styled, TextField, Tooltip, Typography, Avatar, Select, FormControl,
} from "@mui/material";
import {
  Add, SportsEsports, Visibility, Assignment, LibraryBooks,
  Search as SearchIcon, Close as CloseIcon, Groups as GroupsIcon,
  ChevronLeft, ChevronRight, FirstPage, LastPage,
} from "@mui/icons-material";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import sha256 from "crypto-js/sha256";
import BAvatar from "boring-avatars";
import useAuth from "app/hooks/useAuth";
import PageHero from "app/components/page/PageHero";
import api from "app/utils/api";
import { PROJECT_TYPE_COLORS } from "app/utils/constant";
import ProjectTypeChip from "app/components/ProjectTypeChip";
import { FONT_MONO, sweep, pulse } from "app/components/page/pageStyles";

const Container = styled("div")(({ theme }) => ({
  margin: "24px 48px",
  [theme.breakpoints.down("md")]: { margin: "24px 32px" },
  [theme.breakpoints.down("sm")]: { margin: 16 },
}));

// Same per-type avatar palette as the library cards so a project's
// pixel-art identity stays the same wherever it appears.
const AVATAR_PALETTES = {
  rag:   ["#6366f1", "#8b5cf6", "#a78bfa", "#c4b5fd", "#1e1b4b"],
  agent: ["#10b981", "#34d399", "#6ee7b7", "#a7f3d0", "#064e3b"],
  block: ["#6b7280", "#9ca3af", "#d1d5db", "#e5e7eb", "#1f2937"],
};

function getAccent(type) {
  return PROJECT_TYPE_COLORS[type]?.color || "#475569";
}

// ── Same accent-rail tile as the library cards. The page-list version
// only differs in the footer (Open + Playground instead of
// Playground + Clone).
const ProjectCard = styled(Card, {
  shouldForwardProp: (p) => p !== "accent",
})(({ accent }) => ({
  position: "relative",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  borderRadius: 14,
  border: "1px solid rgba(15,23,42,0.08)",
  backgroundColor: "#ffffff",
  overflow: "hidden",
  transition: "transform 0.25s ease, box-shadow 0.25s ease, border-color 0.25s ease",
  "&::before": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background: accent,
    opacity: 0.85,
    pointerEvents: "none",
    zIndex: 2,
  },
  "&::after": {
    content: '""',
    position: "absolute",
    left: 0, right: 0, top: 0, height: 4,
    background:
      "linear-gradient(90deg, transparent, rgba(255,255,255,0.85), transparent)",
    transform: "translateX(-100%)",
    opacity: 0,
    pointerEvents: "none",
    zIndex: 3,
  },
  "&:hover": {
    transform: "translateY(-3px)",
    borderColor: `${accent}66`,
    boxShadow: `0 18px 36px ${accent}1f, 0 4px 10px rgba(15,23,42,0.06)`,
  },
  "&:hover::after": {
    animation: `${sweep} 1.6s ease-out`,
  },
}));

const TYPE_FILTERS = [
  { value: "all",   label: "All types" },
  { value: "agent", label: "Agent" },
  { value: "rag",   label: "RAG" },
  { value: "block", label: "Block" },
];

const SORT_OPTIONS = [
  { value: "recent",   label: "Recently created" },
  { value: "name",     label: "Name (A → Z)" },
  { value: "name_desc",label: "Name (Z → A)" },
  { value: "type",     label: "Type" },
  { value: "team",     label: "Team" },
];

// Page-size options. Defaults to 12 (a clean 4-col × 3-row grid on lg
// breakpoint) and offers 24 / 48 for users who want denser scanning.
const PAGE_SIZE_OPTIONS = [12, 24, 48];

export default function Projects() {
  const { t } = useTranslation();
  const [projects, setProjects] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [sortMode, setSortMode] = useState("recent");
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(() => {
    // Persist user's preference between visits — they set this once
    // and don't want to keep adjusting it.
    try {
      const saved = parseInt(localStorage.getItem("restai_projects_page_size"), 10);
      return PAGE_SIZE_OPTIONS.includes(saved) ? saved : 12;
    } catch { return 12; }
  });
  const auth = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - Projects";
    api.get("/projects", auth.user.token)
      .then((d) => setProjects(d.projects || []))
      .catch(() => {})
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Filter + sort
  const filtered = useMemo(() => {
    let out = projects;
    if (typeFilter !== "all") {
      out = out.filter((p) => p.type === typeFilter);
    }
    if (search.trim()) {
      const needle = search.trim().toLowerCase();
      out = out.filter((p) =>
        (p.name || "").toLowerCase().includes(needle) ||
        (p.human_name || "").toLowerCase().includes(needle) ||
        (p.human_description || "").toLowerCase().includes(needle) ||
        (p.llm || "").toLowerCase().includes(needle) ||
        (p.team?.name || "").toLowerCase().includes(needle) ||
        (p.type || "").toLowerCase().includes(needle)
      );
    }
    const sorted = [...out];
    switch (sortMode) {
      case "name":
        sorted.sort((a, b) => (a.human_name || a.name || "").localeCompare(b.human_name || b.name || ""));
        break;
      case "name_desc":
        sorted.sort((a, b) => (b.human_name || b.name || "").localeCompare(a.human_name || a.name || ""));
        break;
      case "type":
        sorted.sort((a, b) => (a.type || "").localeCompare(b.type || ""));
        break;
      case "team":
        sorted.sort((a, b) => (a.team?.name || "").localeCompare(b.team?.name || ""));
        break;
      case "recent":
      default:
        sorted.sort((a, b) => (b.id || 0) - (a.id || 0));
        break;
    }
    return sorted;
  }, [projects, typeFilter, search, sortMode]);

  // Reset to page 0 whenever the filter / sort / search changes so the
  // user doesn't land on an out-of-range empty page.
  useEffect(() => { setPage(0); }, [typeFilter, search, sortMode]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const safePage = Math.min(page, pageCount - 1);
  const paged = useMemo(
    () => filtered.slice(safePage * pageSize, (safePage + 1) * pageSize),
    [filtered, safePage, pageSize]
  );
  const rangeStart = filtered.length === 0 ? 0 : safePage * pageSize + 1;
  const rangeEnd = Math.min(filtered.length, (safePage + 1) * pageSize);

  const handlePageSize = (size) => {
    setPageSize(size);
    setPage(0);
    try { localStorage.setItem("restai_projects_page_size", String(size)); } catch {}
  };

  // ── Hero stats
  const typeCounts = projects.reduce((acc, p) => {
    const k = p.type || "other";
    acc[k] = (acc[k] || 0) + 1;
    return acc;
  }, {});
  const TYPE_GLYPH = {
    rag:   { glyph: "⌬", color: "#a5b4fc", label: t("projects.type.rag") || "RAG" },
    agent: { glyph: "◈", color: "#86efac", label: t("projects.type.agent") || "Agent" },
    block: { glyph: "⊞", color: "#fcd34d", label: t("projects.type.block") || "Block" },
  };
  const topTypeStats = Object.entries(typeCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([type, count]) => {
      const meta = TYPE_GLYPH[type] || { glyph: "◇", color: "#cbd5f5", label: type };
      return { glyph: meta.glyph, color: meta.color, label: `${count} ${meta.label}` };
    });

  return (
    <Container>
      <PageHero
        icon={<SportsEsports sx={{ color: "#fff" }} />}
        eyebrow="PROJECTS"
        title={t("projects.title") || "Projects"}
        subtitle={t("projects.subtitle")}
        stats={[
          { glyph: "◆", color: "#93c5fd", label: `${projects.length} total` },
          ...topTypeStats,
        ]}
        actions={
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              variant="outlined"
              startIcon={<LibraryBooks />}
              onClick={() => navigate("/projects/library")}
              sx={{
                color: "#fff",
                borderColor: "rgba(255,255,255,0.4)",
                "&:hover": { borderColor: "#fff", background: "rgba(255,255,255,0.08)" },
              }}
            >
              {t("nav.library", "Library")}
            </Button>
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => navigate("/projects/new")}
            >
              {t("projects.newProject")}
            </Button>
          </Box>
        }
      />

      <Box
        sx={{
          mb: 3,
          display: "flex",
          gap: 1.5,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <TextField
          size="small"
          placeholder={t("projects.search") || "Search projects, LLM, team…"}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          sx={{ flex: 1, minWidth: 260 }}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <SearchIcon fontSize="small" sx={{ color: "text.disabled" }} />
              </InputAdornment>
            ),
            endAdornment: search ? (
              <InputAdornment position="end">
                <IconButton size="small" onClick={() => setSearch("")}>
                  <CloseIcon fontSize="small" />
                </IconButton>
              </InputAdornment>
            ) : null,
          }}
        />

        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
          {TYPE_FILTERS.map((f) => {
            const active = typeFilter === f.value;
            const accent = f.value === "all" ? "#475569" : getAccent(f.value);
            return (
              <Chip
                key={f.value}
                label={f.label}
                onClick={() => setTypeFilter(f.value)}
                size="small"
                sx={{
                  height: 30,
                  fontWeight: active ? 700 : 500,
                  cursor: "pointer",
                  color: active ? "#fff" : accent,
                  backgroundColor: active ? accent : `${accent}10`,
                  border: `1px solid ${active ? accent : `${accent}33`}`,
                  transition: "all 0.18s ease",
                  "&:hover": {
                    backgroundColor: active ? accent : `${accent}1c`,
                    transform: "translateY(-1px)",
                  },
                  "& .MuiChip-label": { px: 1.25 },
                }}
              />
            );
          })}
        </Box>

        <TextField
          select
          size="small"
          value={sortMode}
          onChange={(e) => setSortMode(e.target.value)}
          sx={{ width: 200 }}
        >
          {SORT_OPTIONS.map((o) => (
            <MenuItem key={o.value} value={o.value}>{o.label}</MenuItem>
          ))}
        </TextField>
      </Box>

      {/* Result hint — always visible so the user knows the count + range */}
      {!loading && filtered.length > 0 && (
        <Typography
          variant="caption"
          sx={{
            display: "block",
            mb: 2,
            color: "text.secondary",
            fontFamily: FONT_MONO,
            fontSize: "0.7rem",
          }}
        >
          {(search || typeFilter !== "all")
            ? `Showing ${rangeStart}–${rangeEnd} of ${filtered.length} (${projects.length} total)`
            : `Showing ${rangeStart}–${rangeEnd} of ${filtered.length} project${filtered.length === 1 ? "" : "s"}`}
        </Typography>
      )}

      {filtered.length === 0 ? (
        <Box
          sx={{
            py: 10,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 2,
          }}
        >
          <Box
            sx={{
              width: 72,
              height: 72,
              borderRadius: "50%",
              background: "rgba(25,118,210,0.10)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              animation: `${pulse} 3s ease-out infinite`,
            }}
          >
            <Assignment sx={{ fontSize: 36, color: "#1976d2" }} />
          </Box>
          <Box sx={{ textAlign: "center" }}>
            <Typography variant="h6" fontWeight={700} sx={{ mb: 0.5 }}>
              {loading
                ? "Loading…"
                : (search || typeFilter !== "all")
                  ? "No projects match the current filters."
                  : t("projects.emptyTitle")}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {(search || typeFilter !== "all")
                ? "Try adjusting the search or picking a different type."
                : t("projects.emptyMessage")}
            </Typography>
          </Box>
          {!loading && !search && typeFilter === "all" && (
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={() => navigate("/projects/new")}
            >
              {t("projects.newProject")}
            </Button>
          )}
        </Box>
      ) : (
        <>
        <Grid container spacing={3}>
          {paged.map((project) => {
            const accent = getAccent(project.type);
            const users = project.users || [];
            return (
              <Grid item xs={12} sm={6} md={4} lg={3} key={project.id}>
                <ProjectCard elevation={0} accent={accent}>
                  <Box sx={{ p: 2.25, pt: 2.5, pb: 1.5, flex: 1, display: "flex", flexDirection: "column", gap: 1.25 }}>
                    <Box sx={{ display: "flex", gap: 1.5, alignItems: "flex-start" }}>
                      <Box sx={{ flexShrink: 0, mt: 0.25 }}>
                        <BAvatar
                          name={project.name || String(project.id)}
                          size={42}
                          variant="pixel"
                          colors={AVATAR_PALETTES[project.type] || AVATAR_PALETTES.block}
                          square
                        />
                      </Box>
                      <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Tooltip title={project.human_name || project.name} placement="top-start">
                          <Typography
                            variant="subtitle1"
                            sx={{
                              fontWeight: 700,
                              lineHeight: 1.25,
                              color: "text.primary",
                              cursor: "pointer",
                              overflow: "hidden",
                              textOverflow: "ellipsis",
                              whiteSpace: "nowrap",
                              "&:hover": { color: accent },
                              transition: "color 0.15s ease",
                            }}
                            onClick={() => navigate("/project/" + project.id)}
                          >
                            {project.human_name || project.name}
                          </Typography>
                        </Tooltip>
                        <Typography
                          variant="caption"
                          sx={{
                            color: "text.disabled",
                            fontFamily: FONT_MONO,
                            fontSize: "0.65rem",
                            letterSpacing: "0.05em",
                          }}
                        >
                          PROJECT/{String(project.id).padStart(4, "0")}
                        </Typography>
                      </Box>
                    </Box>

                    <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", alignItems: "center" }}>
                      <ProjectTypeChip type={project.type} />
                      {project.llm && (
                        <Chip
                          label={project.llm}
                          size="small"
                          variant="outlined"
                          sx={{
                            height: 22,
                            fontSize: "0.7rem",
                            fontFamily: FONT_MONO,
                            fontWeight: 500,
                            borderColor: "rgba(15,23,42,0.12)",
                            color: "text.secondary",
                            "& .MuiChip-label": { px: 1 },
                          }}
                        />
                      )}
                      {project.team?.name && (
                        <Chip
                          icon={<GroupsIcon sx={{ fontSize: 12 }} />}
                          label={project.team.name}
                          size="small"
                          variant="outlined"
                          sx={{
                            height: 22,
                            fontSize: "0.7rem",
                            fontWeight: 500,
                            borderColor: "rgba(15,23,42,0.12)",
                            color: "text.secondary",
                            "& .MuiChip-label": { px: 0.75 },
                          }}
                        />
                      )}
                    </Box>

                    <Typography
                      variant="body2"
                      sx={{
                        color: project.human_description ? "text.secondary" : "text.disabled",
                        fontStyle: project.human_description ? "normal" : "italic",
                        display: "-webkit-box",
                        WebkitLineClamp: 2,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                        minHeight: "2.6em",
                        lineHeight: 1.45,
                      }}
                    >
                      {project.human_description || "No description provided."}
                    </Typography>

                    {project.system ? (
                      <Box
                        sx={{
                          mt: 0.5,
                          flex: 1,
                          minHeight: 64,
                          background: `linear-gradient(180deg, ${accent}0a, rgba(15,23,42,0.025))`,
                          border: `1px solid ${accent}22`,
                          borderRadius: 1.5,
                          p: 1.25,
                          position: "relative",
                          overflow: "hidden",
                        }}
                      >
                        <Typography
                          sx={{
                            position: "absolute",
                            top: 4, right: 6,
                            fontFamily: FONT_MONO,
                            fontSize: "0.55rem",
                            letterSpacing: "0.18em",
                            color: accent,
                            opacity: 0.7,
                            fontWeight: 600,
                          }}
                        >
                          PROMPT
                        </Typography>
                        <Box
                          sx={{
                            display: "-webkit-box",
                            WebkitLineClamp: 3,
                            WebkitBoxOrient: "vertical",
                            overflow: "hidden",
                            fontFamily: FONT_MONO,
                            fontSize: "0.72rem",
                            lineHeight: 1.55,
                            color: "text.secondary",
                            mt: 1.5,
                            "&::before": {
                              content: '"> "',
                              color: accent,
                              fontWeight: 700,
                            },
                          }}
                        >
                          {project.system.replace(/\s+/g, " ").trim()}
                        </Box>
                      </Box>
                    ) : (
                      <Box sx={{ flex: 1, minHeight: 0 }} />
                    )}
                  </Box>

                  <Box
                    sx={{
                      px: 2.25,
                      py: 1.25,
                      borderTop: "1px solid rgba(15,23,42,0.06)",
                      backgroundColor: "rgba(15,23,42,0.015)",
                      display: "flex",
                      gap: 1,
                      alignItems: "center",
                    }}
                  >
                    <Box sx={{ display: "flex", alignItems: "center", flex: 1, minWidth: 0 }}>
                      {users.length > 0 ? (
                        <>
                          {users.slice(0, 3).map((u, idx) => (
                            <Tooltip key={u.username} title={u.username}>
                              <Avatar
                                src={`https://www.gravatar.com/avatar/${sha256(u.username)}?d=identicon`}
                                sx={{
                                  width: 22,
                                  height: 22,
                                  border: "2px solid #fff",
                                  ml: idx === 0 ? 0 : -0.75,
                                  boxShadow: "0 1px 3px rgba(15,23,42,0.12)",
                                }}
                              />
                            </Tooltip>
                          ))}
                          {users.length > 3 && (
                            <Tooltip title={users.slice(3).map((u) => u.username).join(", ")}>
                              <Avatar
                                sx={{
                                  width: 22, height: 22,
                                  fontSize: "0.62rem",
                                  fontWeight: 700,
                                  fontFamily: FONT_MONO,
                                  border: "2px solid #fff",
                                  ml: -0.75,
                                  bgcolor: "rgba(15,23,42,0.08)",
                                  color: "text.secondary",
                                }}
                              >
                                +{users.length - 3}
                              </Avatar>
                            </Tooltip>
                          )}
                        </>
                      ) : (
                        <Box
                          component="span"
                          sx={{
                            fontSize: "0.65rem",
                            color: "text.disabled",
                            fontStyle: "italic",
                          }}
                        >
                          no members
                        </Box>
                      )}
                    </Box>

                    {/* Playground secondary action */}
                    <Tooltip title={t("projects.actions.playground")}>
                      <IconButton
                        size="small"
                        onClick={() => navigate(`/project/${project.id}/playground`)}
                        sx={{
                          color: accent,
                          border: `1px solid ${accent}33`,
                          borderRadius: 1.25,
                          "&:hover": { borderColor: accent, backgroundColor: `${accent}10` },
                        }}
                      >
                        <SportsEsports fontSize="small" />
                      </IconButton>
                    </Tooltip>

                    <Button
                      size="small"
                      variant="contained"
                      startIcon={<Visibility />}
                      onClick={() => navigate(`/project/${project.id}`)}
                      sx={{
                        textTransform: "none",
                        fontWeight: 600,
                        backgroundColor: accent,
                        boxShadow: "none",
                        "&:hover": {
                          backgroundColor: accent,
                          opacity: 0.9,
                          boxShadow: `0 4px 12px ${accent}55`,
                        },
                      }}
                    >
                      {t("projects.actions.open") || "Open"}
                    </Button>
                  </Box>
                </ProjectCard>
              </Grid>
            );
          })}
        </Grid>

        {/* Pager — only renders when there's more than one page */}
        {pageCount > 1 && (
          <Box
            sx={{
              mt: 4,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 2,
              p: 1.5,
              borderRadius: 2,
              border: "1px solid rgba(15,23,42,0.08)",
              backgroundColor: "rgba(15,23,42,0.015)",
            }}
          >
            <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
              <Typography
                variant="caption"
                sx={{ color: "text.secondary", fontFamily: FONT_MONO, mr: 1 }}
              >
                Per page
              </Typography>
              <FormControl size="small" sx={{ minWidth: 72 }}>
                <Select
                  value={pageSize}
                  onChange={(e) => handlePageSize(Number(e.target.value))}
                  sx={{
                    fontFamily: FONT_MONO,
                    fontSize: "0.78rem",
                    "& .MuiSelect-select": { py: 0.5 },
                  }}
                >
                  {PAGE_SIZE_OPTIONS.map((n) => (
                    <MenuItem key={n} value={n} sx={{ fontFamily: FONT_MONO }}>
                      {n}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Box>

            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <Tooltip title="First page">
                <span>
                  <IconButton
                    size="small"
                    onClick={() => setPage(0)}
                    disabled={safePage === 0}
                  >
                    <FirstPage fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Previous">
                <span>
                  <IconButton
                    size="small"
                    onClick={() => setPage((p) => Math.max(0, p - 1))}
                    disabled={safePage === 0}
                  >
                    <ChevronLeft fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Box
                sx={{
                  px: 1.5,
                  fontFamily: FONT_MONO,
                  fontSize: "0.78rem",
                  fontWeight: 600,
                  color: "text.secondary",
                  minWidth: 80,
                  textAlign: "center",
                }}
              >
                {safePage + 1} / {pageCount}
              </Box>
              <Tooltip title="Next">
                <span>
                  <IconButton
                    size="small"
                    onClick={() => setPage((p) => Math.min(pageCount - 1, p + 1))}
                    disabled={safePage >= pageCount - 1}
                  >
                    <ChevronRight fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
              <Tooltip title="Last page">
                <span>
                  <IconButton
                    size="small"
                    onClick={() => setPage(pageCount - 1)}
                    disabled={safePage >= pageCount - 1}
                  >
                    <LastPage fontSize="small" />
                  </IconButton>
                </span>
              </Tooltip>
            </Box>
          </Box>
        )}
        </>
      )}
    </Container>
  );
}
