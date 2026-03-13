import { useEffect, useState } from "react";
import { Box, Card, CircularProgress } from "@mui/material";
import { toast } from 'react-toastify';
import useAuth from "app/hooks/useAuth";
import { FlexBox } from "app/components/FlexBox";
import { Article } from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import TableRow from '@mui/material/TableRow';
import TableCell from '@mui/material/TableCell';
import ReactJson from '@microlink/react-json-view';


export default function RAGRetrieval({ project }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
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
    return fetch(url + "/projects/" + projectID + "/logs?start=" + start + "&end=" + end, { headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }) })
      .then((res) => {
        if (!res.ok) {
          if (res.status === 404) {
            throw new Error('Logs not found. Permissions?');
          }
          throw new Error('Error fetching logs');
        }
        return res.json();
      })
      .then((d) => {

        if (d.logs) {
          setLogs(d.logs)
          if (d.logs.length === 0) {
            setCount(page * rows);
            setPage(page - 1);
          }
        }
        return d
      }).catch(err => {
        toast.error(err.toString());
      });
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
            //handleViewClick(embeddings[rowMeta.dataIndex]);
            const colSpan = rowData.length;
            return (
              <>
                <TableRow>
                  <TableCell sx={{ p: 2, backgroundColor: "#f0f0f0" }} colSpan={colSpan}>
                    {!log &&
                      <CircularProgress className="circleProgress" />
                    }
                    {log &&
                      <ReactJson src={log} enableClipboard={false} />
                    }
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
        data={logs.map(chunk => [chunk.date, chunk.llm, chunk.question, chunk.answer])}
        columns={[{
          name: "Date",
          options: {
            customHeadRender: ({ index, ...column }) => {
              return (
                <TableCell key={index} style={{ width: "200px" }}>
                  {column.label}
                </TableCell>
              )
            },
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                {new Date(value).toLocaleString()}
              </Box>
            )
          }
        },
        {
          name: "LLM",
          options: {
            filter: false,
            sort: false,
            display: false,
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        },
        {
          name: "Question",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        },
        {
          name: "Answer",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
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

