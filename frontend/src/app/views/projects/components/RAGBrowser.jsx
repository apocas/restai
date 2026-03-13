import { useEffect, useState } from "react";
import { Box, Card, Divider, Button } from "@mui/material";
import { toast } from 'react-toastify';
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { FlexBox } from "app/components/FlexBox";
import { FileUpload, Delete } from "@mui/icons-material";
import MUIDataTable from "mui-datatables";
import TableRow from '@mui/material/TableRow';
import TableCell from '@mui/material/TableCell';
import ReactJson from '@microlink/react-json-view';


export default function RAGBrowser({ project }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [embeddings, setEmbeddings] = useState([]);
  const [rowsExpanded, setRowsExpanded] = useState([]);
  const [embedding, setEmbedding] = useState({ "ids": {}, "metadatas": {}, "documents": {} });
  const [state, setState] = useState({ "chunksize": "512", "splitter": "token" });

  const fetchEmbeddings = (projectID) => {
    setEmbeddings([]);
    if (project.chunks < 30000 || !project.chunks) {
      return fetch(url + "/projects/" + projectID + "/embeddings", {
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      })
        .then((res) => res.json())
        .then((d) => setEmbeddings(d.embeddings)
        ).catch(err => {
          toast.error(err.toString());
        });
    }
  }

  const handleDeleteClick = (embedding) => {
    if (window.confirm("Are you sure you to delete this embedding " + embedding + "?")) {
      fetch(url + "/projects/" + project.id+ "/embeddings/" + btoa(embedding), {
        method: 'DELETE',
        headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
      })
        .then(response => {
          if (!response.ok) {
            throw new Error('Error deleting embedding');
          }
          window.location.reload();
        }).catch(err => {
          console.log(err.toString());
          toast.error("Error deleting embedding");
        });
    }
  };

  const handleViewClick = (source) => {
    fetch(url + "/projects/" + project.id + "/embeddings/source/" + btoa(source), {
      method: 'GET',
      headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
    })
      .then(response => response.json())
      .then(response => {
        response.source = source;
        setEmbedding(response);
        setTimeout(() => {
          //ref.current?.scrollIntoView({ behavior: 'smooth' });
        }, 150);
      }).catch(err => {
        toast.error(err.toString());
      });
  }

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  useEffect(() => {
    fetchEmbeddings(project.id);
  }, []);

  return (
    <Card elevation={3}>
      <FlexBox>
        <FileUpload sx={{ ml: 2, mt: 2 }} />
        <H4 sx={{ p: 2 }}>
          Embeddings Browser
        </H4>
      </FlexBox>

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
                  <TableCell sx={{ p: 2, backgroundColor: "#f0f0f0" }} colSpan={colSpan}><b>IDS:</b> <ReactJson src={embedding.ids} enableClipboard={false} collapsed={0} /></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell sx={{ p: 2, backgroundColor: "#f0f0f0" }} colSpan={colSpan}><b>Metadatas:</b> <ReactJson src={embedding.metadatas} enableClipboard={false} /></TableCell>
                </TableRow>
                <TableRow>
                  <TableCell sx={{ p: 2, backgroundColor: "#f0f0f0" }} colSpan={colSpan}><b>Documents:</b> <ReactJson src={embedding.documents} enableClipboard={false} /></TableCell>
                </TableRow>
              </>);
          },
          onRowExpansionChange: (_, allRowsExpanded) => {
            setRowsExpanded(allRowsExpanded.slice(-1).map(item => item.index))
            if (allRowsExpanded.length > 0) {
              handleViewClick(embeddings[allRowsExpanded[0].dataIndex]);
            }
          }
        }}
        data={embeddings.map(embedding => [embedding, <Button variant="outlined" color="error" onClick={function() {handleDeleteClick(embedding)}} startIcon={<Delete fontSize="small"/>}>
          Delete
        </Button>])}
        columns={[{
          name: "Name",
          options: {
            customBodyRender: (value, tableMeta, updateValue) => (
              <Box display="flex" alignItems="center" gap={4}>
                {value}
              </Box>
            )
          }
        },
        {
          name: "Operations",
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

