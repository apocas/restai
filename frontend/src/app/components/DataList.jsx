import { useState, useMemo } from "react";
import {
  Box, Card, Chip, IconButton, InputAdornment, MenuItem, Select,
  Table, TableBody, TableCell, TableHead, TableRow, TablePagination,
  TableSortLabel, TextField, Tooltip, Typography, styled,
} from "@mui/material";
import { Search, Inbox } from "@mui/icons-material";

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
 *  - emptyMessage: string
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
  emptyMessage = "No items found",
  defaultSort = null,
  pageSize = 10,
}) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState(defaultSort?.key || null);
  const [sortDir, setSortDir] = useState(defaultSort?.direction || "asc");
  const [filterValues, setFilterValues] = useState({});
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(pageSize);

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

  const hasToolbar = searchKeys.length > 0 || filters.length > 0;

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
              placeholder="Search..."
              value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(0); }}
              sx={{ flex: 1, minWidth: 220 }}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <Search fontSize="small" color="action" />
                  </InputAdornment>
                ),
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
                if (!selected || selected === "__all__") return `${f.label}: All`;
                const opt = f.options.find((o) => String(o.value) === String(selected));
                return `${f.label}: ${opt?.label || selected}`;
              }}
            >
              <MenuItem value="__all__">{f.label}: All</MenuItem>
              {f.options.map((opt) => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          ))}
          <Box sx={{ flex: "0 0 auto", ml: "auto" }}>
            <Chip label={`${sorted.length} result${sorted.length !== 1 ? "s" : ""}`} size="small" variant="outlined" />
          </Box>
        </ToolbarRow>
      )}

      {paged.length === 0 ? (
        <EmptyState>
          <Inbox sx={{ fontSize: 48, opacity: 0.4 }} />
          <Typography variant="body2">{emptyMessage}</Typography>
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
              {paged.map((row) => (
                <StyledTableRow
                  key={rowKey(row)}
                  clickable={onRowClick ? "true" : "false"}
                  onClick={onRowClick ? (e) => {
                    // Don't fire row click on action button clicks
                    if (e.target.closest("button, a")) return;
                    onRowClick(row);
                  } : undefined}
                >
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
              ))}
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
