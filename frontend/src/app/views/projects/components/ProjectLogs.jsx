import { useEffect, useState } from "react";
import { Box, Card, Chip, CircularProgress, Collapse, Typography } from "@mui/material";
import useAuth from "app/hooks/useAuth";
import { FlexBox } from "app/components/FlexBox";
import { Article } from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import TableRow from '@mui/material/TableRow';
import TableCell from '@mui/material/TableCell';
import ReactJson from '@microlink/react-json-view';
import api from "app/utils/api";


export default function RAGRetrieval({ project }) {
  const auth = useAuth();
  const [rowsExpanded, setRowsExpanded] = useState([]);
  const [logs, setLogs] = useState([]);
  const [log, setLog] = useState({});
  const [state, setState] = useState({ search: "" });
  const [start, setStart] = useState(0);
  const [rows, setRows] = useState(10);
  const [end, setEnd] = useState(rows);
  const [page, setPage] = useState(0);
  const [count, setCount] = useState(1000000);


  const fetchLogs = (projectID) => {
    auth.checkAuth();
    return api.get("/projects/" + projectID + "/logs?start=" + start + "&end=" + end, auth.user.token)
      .then((d) => {
        if (d.logs) {
          setLogs(d.logs)
          if (d.logs.length === 0 && page > 0) {
            setCount(page * rows);
            setPage(page - 1);
          }
        }
        return d
      }).catch(() => {});
  }

  const handleViewClick = (source) => {
    setLog(source);
  }

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };


  const changePage = (page, sortOrder) => {
    setPage(page);
  };


  useEffect(() => {
    if (project.name)
      fetchLogs(project.id);
  }, [project, start, end]);

  useEffect(() => {
    setStart(page * rows);
    setEnd((page * rows) + rows);
  }, [page, rows]);

  return (
    <Card elevation={3}>
      <MUIDataTable
        title={
          <FlexBox alignItems="center">
            <Article sx={{ ml: 0, mr: 2 }} />
            <h2>Logs</h2>
          </FlexBox>
        }
        options={{
          "print": false,
          "selectableRows": "none",
          "expandableRows": true,
          "expandableRowsHeader": false,
          "expandableRowsOnClick": true,
          "download": false,
          "filter": true,
          "viewColumns": false,
          "rowsExpanded": rowsExpanded,
          "rowsPerPage": rows,
          "rowsPerPageOptions": [10, 50, 100, 500, 1000],
          "elevation": 0,
          "count": count,
          "serverSide": true,
          "textLabels": {
            body: {
              noMatch: "No logs found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          },
          "onTableChange": (action, tableState) => {
            console.log(action, tableState);
            switch (action) {
              case 'changePage':
                changePage(tableState.page, tableState.sortOrder);
                break;
              case 'changeRowsPerPage':
                setRows(tableState.rowsPerPage);
                break;
              case 'sort':
                this.sort(tableState.page, tableState.sortOrder);
                break;
              default:
                console.log('action not handled.');
            }
          },
          customSearch: (searchQuery, currentRow, columns) => {
            let isFound = false;
            currentRow.forEach(col => {
              if (col && col.toString().indexOf(searchQuery) >= 0) {
                isFound = true;
              }
            });
            return isFound;
          },
          isRowExpandable: (dataIndex, expandedRows) => {
            return true;
          },
          renderExpandableRow: (rowData, rowMeta) => {
            const colSpan = rowData.length;
            const contextData = log?.context ? (() => { try { return JSON.parse(log.context); } catch { return null; } })() : null;
            const attachmentsData = log?.attachments ? (() => { try { return JSON.parse(log.attachments); } catch { return null; } })() : null;
            const imageSrc = log?.image ? (log.image.startsWith("data:") ? log.image : `data:image/png;base64,${log.image}`) : null;
            return (
              <>
                <TableRow>
                  <TableCell sx={{ p: 2, backgroundColor: "#f0f0f0" }} colSpan={colSpan}>
                    {!log &&
                      <CircularProgress className="circleProgress" />
                    }
                    {log && (
                      <Box>
                        {log.status && log.status !== "success" && log.error && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>Error</Typography>
                            <Box sx={{
                              p: 1.5, borderRadius: 1, fontFamily: "monospace", fontSize: "0.8rem",
                              backgroundColor: "#fff6f6", border: "1px solid #e0b4b4", color: "#9f3a38",
                              whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto",
                            }}>
                              {log.error}
                            </Box>
                          </Box>
                        )}
                        {imageSrc && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>Uploaded Image</Typography>
                            <img
                              src={imageSrc}
                              alt="user attachment"
                              style={{ maxWidth: 320, maxHeight: 240, borderRadius: 4, border: "1px solid #e0e0e0" }}
                            />
                          </Box>
                        )}
                        {attachmentsData && attachmentsData.length > 0 && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>File Attachments</Typography>
                            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                              {attachmentsData.map((a, i) => (
                                <Chip
                                  key={i}
                                  label={`${a.name}${a.size ? ` (${Math.round(a.size / 1024)} KB)` : ""}`}
                                  size="small"
                                  variant="outlined"
                                />
                              ))}
                            </Box>
                          </Box>
                        )}
                        {log.system_prompt && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>System Prompt</Typography>
                            <Box sx={{
                              p: 1.5, borderRadius: 1, fontFamily: "monospace", fontSize: "0.8rem",
                              backgroundColor: "#fff", border: "1px solid #e0e0e0",
                              whiteSpace: "pre-wrap", maxHeight: 200, overflow: "auto",
                            }}>
                              {log.system_prompt}
                            </Box>
                          </Box>
                        )}
                        {contextData && (
                          <Box sx={{ mb: 2 }}>
                            <Typography variant="caption" fontWeight={600} sx={{ display: "block", mb: 0.5 }}>Context</Typography>
                            <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap" }}>
                              {Object.entries(contextData).map(([k, v]) => (
                                <Chip key={k} label={`${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`} size="small" variant="outlined" />
                              ))}
                            </Box>
                          </Box>
                        )}
                        <ReactJson src={log} enableClipboard={false} collapsed={1} />
                      </Box>
                    )}
                  </TableCell>
                </TableRow>
              </>);
          },
          onRowExpansionChange: (_, allRowsExpanded) => {
            setRowsExpanded(allRowsExpanded.slice(-1).map(item => item.index))
            if (allRowsExpanded.length > 0) {
              handleViewClick(logs[allRowsExpanded[0].dataIndex]);
            }
          }
        }}
        data={logs.map(chunk => [
          chunk.status || "success",
          chunk.date,
          chunk.llm,
          // Pass the whole row so the Question cell can render image thumbnail
          // + attachment chips alongside the question text without needing
          // more server-side plumbing.
          chunk,
          chunk.answer,
        ])}
        columns={[{
          name: "Status",
          options: {
            filter: true,
            customHeadRender: ({ index, ...column }) => (
              <TableCell key={index} style={{ width: "110px" }}>
                {column.label}
              </TableCell>
            ),
            customBodyRender: (value) => {
              const colorMap = {
                success: "success",
                error: "error",
                guard_block: "warning",
                rate_limit: "warning",
                budget: "warning",
              };
              const label = value === "success"
                ? "OK"
                : (value === "guard_block" ? "guard" : value);
              return (
                <Chip size="small" label={label} color={colorMap[value] || "default"} />
              );
            },
          },
        },
        {
          name: "Date",
          options: {
            customHeadRender: ({ index, ...column }) => (
              <TableCell key={index} style={{ width: "180px" }}>
                {column.label}
              </TableCell>
            ),
            customBodyRender: (value) => (
              <Box display="flex" alignItems="center" gap={4}>
                {new Date(value).toLocaleString()}
              </Box>
            ),
          }
        },
        {
          name: "LLM",
          options: {
            filter: false,
            sort: false,
            display: false,
            customBodyRender: (value) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        },
        {
          name: "Question",
          options: {
            customBodyRender: (row) => {
              if (!row) return null;
              const imageSrc = row.image ? (row.image.startsWith("data:") ? row.image : `data:image/png;base64,${row.image}`) : null;
              let attachments = [];
              if (row.attachments) {
                try { attachments = JSON.parse(row.attachments) || []; } catch { attachments = []; }
              }
              return (
                <Box display="flex" alignItems="flex-start" gap={1} sx={{ flexWrap: "wrap" }}>
                  {imageSrc && (
                    <img
                      src={imageSrc}
                      alt=""
                      style={{ width: 48, height: 48, objectFit: "cover", borderRadius: 4, border: "1px solid #e0e0e0", flexShrink: 0 }}
                    />
                  )}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Box>{row.question}</Box>
                    {attachments.length > 0 && (
                      <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
                        {attachments.map((a, i) => (
                          <Chip
                            key={i}
                            label={a.name}
                            size="small"
                            variant="outlined"
                            sx={{ fontSize: "0.7rem", height: 20 }}
                          />
                        ))}
                      </Box>
                    )}
                  </Box>
                </Box>
              );
            },
          }
        },
        {
          name: "Answer",
          options: {
            customBodyRender: (value) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        }]}
      />

    </Card>
  );
}

