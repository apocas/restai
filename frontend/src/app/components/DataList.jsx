import { useState, useMemo } from "react";
import {
  Box, Button, Card, Checkbox, Chip, IconButton, InputAdornment, MenuItem, Select,
  Table, TableBody, TableCell, TableHead, TableRow, TablePagination,
  TableSortLabel, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { Search, Inbox, Close, SearchOff } from "@mui/icons-material";
import { useTranslation } from "react-i18next";

const StyledCard = styled(Card)(({ theme }) => ({
  borderRadius: 12,
  border: "1px solid",
  borderColor: theme.palette.divider,
  overflow: "hidden",
}));

const Header = styled(Box)(({ theme }) => ({
  padding: "20px 24px 16px",
  borderBottom: `1px solid ${theme.palette.divider}`,
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: theme.spacing(2),
  flexWrap: "wrap",
}));

const ToolbarRow = styled(Box)(({ theme }) => ({
  padding: "14px 24px",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(2),
  flexWrap: "wrap",
  borderBottom: `1px solid ${theme.palette.divider}`,
}));

// Shown above the table when one or more rows are selected (bulkActions
// opt-in). Sits between the toolbar and the table so the selection
// count + action buttons are unmistakable.
const BulkActionBar = styled(Box)(({ theme }) => ({
  padding: "10px 24px",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(1.5),
  backgroundColor: theme.palette.action.selected,
  borderBottom: `1px solid ${theme.palette.divider}`,
  flexWrap: "wrap",
}));

const StyledTableRow = styled(TableRow)(({ theme, clickable }) => ({
  "& td": {
    borderBottom: `1px solid ${theme.palette.divider}`,
    padding: "14px 16px",
  },
  "& td:first-of-type": { paddingLeft: 24 },
  "& td:last-of-type": { paddingRight: 24 },
  "&:last-child td": { borderBottom: "none" },
  ...(clickable === "true" && {
    cursor: "pointer",
    "&:hover": {
      backgroundColor: theme.palette.action.hover,
    },
  }),
}));

const EmptyState = styled(Box)(({ theme }) => ({
  padding: "60px 24px",
  textAlign: "center",
  color: theme.palette.text.secondary,
  display: "flex",
  flexDirection: "column",
  alignItems: "center",
  gap: theme.spacing(1),
}));

/**
 * Generic data list with search, filter, sort, pagination.
 *
 * Props:
 *  - title: string — header title
 *  - subtitle: string — header description (optional)
 *  - data: array — rows
 *  - columns: [{ key, label, sortable, align, render(row), width }]
 *  - searchKeys: array of field paths to search (supports dot notation)
 *  - filters: [{ key, label, options: [{ value, label }], getValue(row) }]
 *  - onRowClick: (row) => void — makes rows clickable
 *  - rowKey: (row) => string — default: row.id
 *  - actions: (row) => ReactNode — right-side action buttons per row
 *  - headerAction: ReactNode — right-side header button (e.g. "New")
 *  - emptyMessage: string — fallback text when `emptyState` is not provided
 *  - emptyState: { icon, title, message, actionLabel, onAction } — rich
 *    empty-state block (shown when data.length === 0). `icon` is a
 *    component class (e.g. `Group`). Falls back to Inbox + emptyMessage
 *    when the prop is omitted.
 *  - bulkActions: [{ label, icon, color, onClick(selectedRows) }] — when
 *    non-empty, renders a select-column + a bulk-action bar. Parent
 *    handles the API calls; DataList just hands back selected rows and
 *    clears the selection after each action.
 *  - defaultSort: { key, direction }
 *  - pageSize: default 10
 */
export default function DataList({
  title,
  subtitle,
  data = [],
  columns,
  searchKeys = [],
  filters = [],
  onRowClick,
  rowKey = (row) => row.id,
  actions,
  headerAction,
  emptyMessage,
  emptyState = null,
  bulkActions = [],
  defaultSort = null,
  pageSize = 10,
}) {
  const { t } = useTranslation();
  const effectiveEmptyMessage = emptyMessage ?? t("dataList.noResults");
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState(defaultSort?.key || null);
  const [sortDir, setSortDir] = useState(defaultSort?.direction || "asc");
  const [filterValues, setFilterValues] = useState({});
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize);
  // Set of selected row keys. Stored as a Set so toggling is O(1) and
  // the parent can read size via .size. Cleared whenever the filtered
  // view changes so hidden rows don't silently stay selected.
  const [selectedKeys, setSelectedKeys] = useState(() => new Set());

  const getNested = (obj, path) => {
    if (!obj || !path) return "";
    return path.split(".").reduce((acc, part) => (acc == null ? acc : acc[part]), obj);
  };

  const matchesSearch = (row) => {
    if (!search) return true;
    const needle = search.toLowerCase();
    return searchKeys.some((key) => {
      const value = getNested(row, key);
      if (value == null) return false;
      return String(value).toLowerCase().includes(needle);
    });
  };

  const matchesFilters = (row) => {
    return filters.every((f) => {
      const selected = filterValues[f.key];
      if (!selected || selected === "__all__") return true;
      const rowValue = f.getValue ? f.getValue(row) : getNested(row, f.key);
      return String(rowValue) === String(selected);
    });
  };

  const sorted = useMemo(() => {
    let result = data.filter((row) => matchesSearch(row) && matchesFilters(row));
    if (sortKey) {
      const col = columns.find((c) => c.key === sortKey);
      const getter = col?.sortValue || ((row) => getNested(row, sortKey));
      result = [...result].sort((a, b) => {
        const av = getter(a);
        const bv = getter(b);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        if (typeof av === "number" && typeof bv === "number") {
          return sortDir === "asc" ? av - bv : bv - av;
        }
        return sortDir === "asc"
          ? String(av).localeCompare(String(bv))
          : String(bv).localeCompare(String(av));
      });
    }
    return result;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, search, sortKey, sortDir, filterValues, columns]);

  const paged = useMemo(() => {
    const start = page * rowsPerPage;
    return sorted.slice(start, start + rowsPerPage);
  }, [sorted, page, rowsPerPage]);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  // ── Bulk selection helpers ─────────────────────────────────────────
  const bulkEnabled = bulkActions.length > 0;
  const pagedKeys = useMemo(() => paged.map(rowKey), [paged, rowKey]);
  const allPageSelected = pagedKeys.length > 0 && pagedKeys.every((k) => selectedKeys.has(k));
  const somePageSelected = pagedKeys.some((k) => selectedKeys.has(k));

  const toggleRow = (row) => {
    const k = rowKey(row);
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  };
  const toggleAllOnPage = () => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (allPageSelected) {
        pagedKeys.forEach((k) => next.delete(k));
      } else {
        pagedKeys.forEach((k) => next.add(k));
      }
      return next;
    });
  };
  const clearSelection = () => setSelectedKeys(new Set());

  const runBulkAction = (action) => {
    const selectedRows = data.filter((row) => selectedKeys.has(rowKey(row)));
    if (selectedRows.length === 0) return;
    // Hand rows to the consumer; they're responsible for API calls and
    // refreshing `data`. Clear selection so stale keys don't linger on
    // rows that the parent just deleted.
    Promise.resolve(action.onClick(selectedRows)).finally(clearSelection);
  };

  // ── Render ─────────────────────────────────────────────────────────
  const hasToolbar = searchKeys.length > 0 || filters.length > 0;
  const selectedCount = selectedKeys.size;
  const searching = search.length > 0;
  const hasData = data.length > 0;

  return (
    <StyledCard elevation={0}>
      {(title || headerAction) && (
        <Header>
          <Box>
            {title && <Typography variant="h6" fontWeight={700}>{title}</Typography>}
            {subtitle && (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                {subtitle}
              </Typography>
            )}
          </Box>
          {headerAction}
        </Header>
      )}

      {hasToolbar && (
        <ToolbarRow>
          {searchKeys.length > 0 && (
            <TextField
              size="small"
              placeholder={t("dataList.search")}
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              sx={{ flex: 1, minWidth: 220 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search fontSize="small" color="action" />
                  </InputAdornment>
                ),
                endAdornment: searching ? (
                  <InputAdornment position="end">
                    <Tooltip title={t("dataList.clearSearch")}>
                      <IconButton
                        size="small" edge="end" aria-label={t("dataList.clearSearch")}
                        onClick={() => { setSearch(""); setPage(0); }}
                      >
                        <Close fontSize="small" />
                      </IconButton>
                    </Tooltip>
                  </InputAdornment>
                ) : null,
              }}
            />
          )}
          {filters.map((f) => (
            <Select
              key={f.key}
              size="small"
              value={filterValues[f.key] || "__all__"}
              onChange={(e) => {
                setFilterValues({ ...filterValues, [f.key]: e.target.value });
                setPage(0);
              }}
              sx={{ minWidth: 160 }}
              displayEmpty
              renderValue={(selected) => {
                if (!selected || selected === "__all__") return `${f.label}: ${t("common.all")}`;
                const opt = f.options.find((o) => String(o.value) === String(selected));
                return `${f.label}: ${opt?.label || selected}`;
              }}
            >
              <MenuItem value="__all__">{f.label}: {t("common.all")}</MenuItem>
              {f.options.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          ))}
          <Box sx={{ flex: "0 0 auto", ml: "auto" }}>
            <Chip label={t("common.resultCount", { count: sorted.length })} size="small" variant="outlined" />
          </Box>
        </ToolbarRow>
      )}

      {bulkEnabled && selectedCount > 0 && (
        <BulkActionBar>
          <Typography variant="body2" fontWeight={600}>
            {t("dataList.selected", { count: selectedCount })}
          </Typography>
          {bulkActions.map((a, i) => (
            <Button
              key={i}
              size="small"
              variant="outlined"
              color={a.color || "primary"}
              startIcon={a.icon}
              onClick={() => runBulkAction(a)}
            >
              {a.label}
            </Button>
          ))}
          <Button size="small" onClick={clearSelection} sx={{ ml: "auto" }}>
            {t("dataList.clear")}
          </Button>
        </BulkActionBar>
      )}

      {paged.length === 0 ? (
        <EmptyState>
          {/* Three distinct empty-states:
              1. Searched, no matches → "no matches" + clear-search CTA.
              2. Data present but no rich empty-state provided → plain text.
              3. No data at all, rich empty-state provided → icon + title + action. */}
          {searching && hasData ? (
            <>
              <SearchOff sx={{ fontSize: 48, opacity: 0.4 }} />
              <Typography variant="body2">
                {t("dataList.noMatches", { query: search })}
              </Typography>
              <Button size="small" onClick={() => { setSearch(""); setPage(0); }}>
                {t("dataList.clearSearch")}
              </Button>
            </>
          ) : !hasData && emptyState ? (
            <>
              {emptyState.icon ? (
                <Box
                  sx={{
                    width: 72, height: 72, borderRadius: "50%",
                    display: "flex", alignItems: "center", justifyContent: "center",
                    backgroundColor: "action.hover", mb: 1,
                  }}
                >
                  <emptyState.icon sx={{ fontSize: 36, color: "text.secondary" }} />
                </Box>
              ) : (
                <Inbox sx={{ fontSize: 48, opacity: 0.4 }} />
              )}
              {emptyState.title && (
                <Typography variant="subtitle1" fontWeight={600} sx={{ color: "text.primary" }}>
                  {emptyState.title}
                </Typography>
              )}
              <Typography variant="body2" sx={{ maxWidth: 360 }}>
                {emptyState.message || effectiveEmptyMessage}
              </Typography>
              {emptyState.actionLabel && emptyState.onAction && (
                <Button
                  size="small" variant="contained"
                  startIcon={emptyState.actionIcon}
                  onClick={emptyState.onAction}
                  sx={{ mt: 1 }}
                >
                  {emptyState.actionLabel}
                </Button>
              )}
            </>
          ) : (
            <>
              <Inbox sx={{ fontSize: 48, opacity: 0.4 }} />
              <Typography variant="body2">{effectiveEmptyMessage}</Typography>
            </>
          )}
        </EmptyState>
      ) : (
        <Box sx={{ overflowX: "auto" }}>
          <Table>
            <TableHead>
              <TableRow
                sx={{
                  "& th:first-of-type": { paddingLeft: "24px" },
                  "& th:last-of-type": { paddingRight: "24px" },
                }}
              >
                {bulkEnabled && (
                  <TableCell
                    padding="checkbox"
                    sx={{ backgroundColor: "action.hover", borderBottom: "1px solid", borderColor: "divider" }}
                  >
                    <Checkbox
                      size="small"
                      checked={allPageSelected}
                      indeterminate={!allPageSelected && somePageSelected}
                      onChange={toggleAllOnPage}
                      inputProps={{ "aria-label": "select all on page" }}
                    />
                  </TableCell>
                )}
                {columns.map((col) => (
                  <TableCell
                    key={col.key}
                    align={col.align || "left"}
                    sx={{
                      fontWeight: 600,
                      fontSize: "0.78rem",
                      textTransform: "uppercase",
                      letterSpacing: "0.5px",
                      color: "text.secondary",
                      backgroundColor: "action.hover",
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      width: col.width,
                    }}
                  >
                    {col.sortable ? (
                      <TableSortLabel
                        active={sortKey === col.key}
                        direction={sortKey === col.key ? sortDir : "asc"}
                        onClick={() => handleSort(col.key)}
                      >
                        {col.label}
                      </TableSortLabel>
                    ) : (
                      col.label
                    )}
                  </TableCell>
                ))}
                {actions && <TableCell align="right" sx={{ backgroundColor: "action.hover" }} />}
              </TableRow>
            </TableHead>
            <TableBody>
              {paged.map((row) => {
                const k = rowKey(row);
                const isSelected = selectedKeys.has(k);
                return (
                  <StyledTableRow
                    key={k}
                    clickable={onRowClick ? "true" : "false"}
                    selected={isSelected}
                    onClick={onRowClick ? (e) => {
                      // Don't fire row click on action button clicks / checkbox clicks.
                      if (e.target.closest("button, a, input")) return;
                      onRowClick(row);
                    } : undefined}
                  >
                    {bulkEnabled && (
                      <TableCell padding="checkbox">
                        <Checkbox
                          size="small"
                          checked={isSelected}
                          onChange={() => toggleRow(row)}
                          onClick={(e) => e.stopPropagation()}
                          inputProps={{ "aria-label": `select row ${k}` }}
                        />
                      </TableCell>
                    )}
                    {columns.map((col) => (
                      <TableCell key={col.key} align={col.align || "left"}>
                        {col.render ? col.render(row) : getNested(row, col.key)}
                      </TableCell>
                    ))}
                    {actions && (
                      <TableCell align="right" sx={{ whiteSpace: "nowrap" }}>
                        {actions(row)}
                      </TableCell>
                    )}
                  </StyledTableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      )}

      {sorted.length > rowsPerPage && (
        <TablePagination
          component="div"
          count={sorted.length}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => {
            setRowsPerPage(parseInt(e.target.value, 10));
            setPage(0);
          }}
          rowsPerPageOptions={[10, 25, 50, 100]}
        />
      )}
    </StyledCard>
  );
}
