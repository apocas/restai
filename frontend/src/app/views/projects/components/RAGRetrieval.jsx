import { useEffect, useState } from "react";
import { Box, Card, Divider, Button, TextField, Grid, CircularProgress } from "@mui/material";
import { toast } from 'react-toastify';
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { FlexBox } from "app/components/FlexBox";
import { FileUpload, Delete } from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import TableRow from '@mui/material/TableRow';
import TableCell from '@mui/material/TableCell';
import ReactJson from '@microlink/react-json-view';


export default function RAGRetrieval({ project }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [chunks, setChunks] = useState([]);
  const [rowsExpanded, setRowsExpanded] = useState([]);
  const [embedding, setEmbedding] = useState(null);
  const [state, setState] = useState({ "chunksize": "512", "splitter": "token" });


  const handleSearchClick = () => {
    var data = {}
    data.text = state.search
    data.k = state.k
    data.score = state.cutoff

    fetch(url + "/projects/" + project.id + "/embeddings/search", {
      method: 'POST',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      body: JSON.stringify(data),
    })
      .then(function (response) {
        if (!response.ok) {
          response.json().then(function (data) {
            toast.error(data.detail);
          });
          throw Error(response.statusText);
        } else {
          return response.json();
        }
      })
      .then((response) => {
        if (response.embeddings.length === 0) {
          toast.warning("No embeddings found for this query. Decrease the score cutoff parameter.");
        }
        setChunks(response.embeddings);
      }).catch(err => {
        toast.error(err.toString());
      });
  }

  const handleViewClick = (source) => {
    setEmbedding(null);
    fetch(url + "/projects/" + project.id + "/embeddings/id/" + source.id, {
      method: 'GET',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
    })
      .then(response => response.json())
      .then(response => {
        setEmbedding(response);
      }).catch(err => {
        toast.error(err.toString());
      });
  }

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  return (
    <Card elevation={3}>
      <FlexBox>
        <FileUpload sx={{ ml: 2, mt: 2 }} />
        <H4 sx={{ p: 2 }}>
          Embeddings Search
        </H4>
      </FlexBox>

      <Grid container spacing={3} sx={{ p: 2 }}>
        <Grid item sm={12} xs={12}>
          <TextField
            fullWidth
            InputLabelProps={{ shrink: true }}
            name="search"
            label="Search"
            variant="outlined"
            onChange={handleChange}
          />
        </Grid>
        <Grid item sm={6} xs={12}>
          <TextField
            fullWidth
            InputLabelProps={{ shrink: true }}
            name="cutoff"
            label="Cutoff"
            variant="outlined"
            onChange={handleChange}
            defaultValue={0}
          />
        </Grid>
        <Grid item sm={6} xs={12}>
          <TextField
            fullWidth
            InputLabelProps={{ shrink: true }}
            name="k"
            label="K"
            variant="outlined"
            onChange={handleChange}
            defaultValue={4}
          />
        </Grid>
        <Grid item sm={12} xs={12}>
          <Button variant="outlined" color="success" onClick={handleSearchClick} startIcon={<Delete fontSize="small" />}>
            Search
          </Button>
        </Grid>
      </Grid>
      <Divider />

      <MUIDataTable
        options={{
          "print": false,
          "selectableRows": "none",
          "expandableRows": true,
          "expandableRowsHeader": false,
          "expandableRowsOnClick": true,
          "download": false,
          "filter": true,
          "viewColumns": false,
          rowsExpanded: rowsExpanded,
          "rowsPerPage": 25,
          "elevation": 0,
          "textLabels": {
            body: {
              noMatch: "No embeddings found",
              toolTip: "Sort",
              columnHeaderTooltip: column => `Sort for ${column.label}`
            },
          },
          isRowExpandable: (dataIndex, expandedRows) => {
            return true;
          },
          renderExpandableRow: (rowData, rowMeta) => {
            //handleViewClick(embeddings[rowMeta.dataIndex]);
            const colSpan = rowData.length + 1;
            return (
              <>
                <TableRow>
                  <TableCell sx={{ p: 2, backgroundColor: "#f0f0f0" }} colSpan={colSpan}>
                    {!embedding &&
                      <CircularProgress className="circleProgress" />
                    }
                    {embedding &&
                      <ReactJson src={embedding} enableClipboard={false} />
                    }
                  </TableCell>
                </TableRow>
              </>);
          },
          onRowExpansionChange: (_, allRowsExpanded) => {
            setRowsExpanded(allRowsExpanded.slice(-1).map(item => item.index))
            if (allRowsExpanded.length > 0) {
              handleViewClick(chunks[allRowsExpanded[0].dataIndex]);
            }
          }
        }}
        data={chunks.map(chunk => [chunk.id, chunk.source, chunk.score])}
        columns={[{
          name: "ID",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        },
        {
          name: "Source",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        },
        {
          name: "Score",
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

