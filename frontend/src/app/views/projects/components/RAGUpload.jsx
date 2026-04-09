import { useEffect, useState } from "react";
import {
  Card, Grid, MenuItem, styled, TextField, Tabs, Tab, Typography, Box, ListItemText,
} from "@mui/material";
import Publish from "@mui/icons-material/Publish";
import { useDropzone } from "react-dropzone";
import { toast } from "react-toastify";
import useAuth from "app/hooks/useAuth";
import api from "app/utils/api";
import { FlexAlignCenter } from "app/components/FlexBox";
import { FileUpload } from "@mui/icons-material";
import { convertHexToRGB } from "app/utils/utils";
import { LoadingButton } from "@mui/lab";

const SectionTitle = styled(Typography)(({ theme }) => ({
  fontWeight: 600,
  fontSize: "0.9rem",
  display: "flex",
  alignItems: "center",
  gap: theme.spacing(0.5),
  color: theme.palette.text.secondary,
  marginBottom: theme.spacing(1.5),
}));

const DropZone = styled(FlexAlignCenter)(({ isDragActive, theme }) => ({
  height: 160,
  width: "100%",
  cursor: "pointer",
  borderRadius: "4px",
  marginBottom: "16px",
  transition: "all 350ms ease-in-out",
  border: `2px dashed rgba(${convertHexToRGB(theme.palette.text.primary)}, 0.3)`,
  "&:hover": {
    background: `rgb(${convertHexToRGB(theme.palette.text.primary)}, 0.2) !important`,
  },
  background: isDragActive ? "rgb(0, 0, 0, 0.15)" : "rgb(0, 0, 0, 0.01)",
}));

export default function RAGUpload({ project }) {
  const auth = useAuth();
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState({
    chunksize: "512",
    splitter: "token",
    method: "auto",
  });
  const { getRootProps, getInputProps, acceptedFiles } = useDropzone({
    maxFiles: 1,
    multiple: false,
  });
  const [tabIndex, setTabIndex] = useState(0);
  const handleTabChange = (e, value) => setTabIndex(value);

  const showChunkSettings = state.method === "classic";

  const handleSubmit = async (event) => {
    event.preventDefault();
    setLoading(true);

    if (tabIndex === 0) {
      const formData = new FormData();
      formData.append("file", files[0]);
      formData.append("method", state.method);

      if (showChunkSettings) {
        formData.append("splitter", state.splitter);
        formData.append("chunks", state.chunksize);
      }

      try {
        const result = await api.post("/projects/" + project.id + "/embeddings/ingest/upload", formData, auth.user.token);
        if (result.method) {
          toast.success(`Ingested with ${result.method} method — ${result.chunks} chunks`);
        }
        window.location.reload();
      } catch (err) {
        // errors auto-toasted
      } finally {
        setLoading(false);
      }
    } else if (tabIndex === 1) {
      var body = {
        url: state.url,
        splitter: state.splitter,
        chunks: state.chunksize,
      };

      try {
        await api.post("/projects/" + project.id + "/embeddings/ingest/url", body, auth.user.token);
        window.location.reload();
      } catch (err) {
        // errors auto-toasted
      } finally {
        setLoading(false);
      }
    }
  };

  const handleChange = (event) => {
    if (event && event.persist) event.persist();
    setState({ ...state, [event.target.name]: event.target.value });
  };

  useEffect(() => {
    setFiles(acceptedFiles);
  }, [acceptedFiles]);

  return (
    <Card elevation={1} sx={{ p: 2.5 }}>
      <SectionTitle><FileUpload fontSize="small" /> Ingest Data</SectionTitle>

      <form onSubmit={handleSubmit}>
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12}>
            <TextField
              fullWidth select size="small"
              name="method" label="Ingestion Method" variant="outlined"
              onChange={handleChange} value={state.method}
            >
              <MenuItem value="auto">
                <ListItemText primary="Auto" secondary="Docling → MarkItDown → Classic" />
              </MenuItem>
              <MenuItem value="docling">
                <ListItemText primary="Docling" secondary="Deep-learning, best for complex PDFs" />
              </MenuItem>
              <MenuItem value="markitdown">
                <ListItemText primary="MarkItDown" secondary="Broad format support (DOCX, XLSX, PPTX)" />
              </MenuItem>
              <MenuItem value="classic">
                <ListItemText primary="Classic" secondary="LlamaIndex readers, basic text extraction" />
              </MenuItem>
            </TextField>
          </Grid>

          {showChunkSettings && (
            <>
              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth select size="small"
                  name="splitter" label="Splitter" variant="outlined"
                  onChange={handleChange} value={state.splitter}
                >
                  {["token", "sentence"].map((item) => (
                    <MenuItem value={item} key={item}>{item}</MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField
                  fullWidth select size="small"
                  name="chunksize" label="Chunk Size" variant="outlined"
                  onChange={handleChange} value={state.chunksize}
                >
                  {["126", "256", "512", "1024", "2048"].map((item) => (
                    <MenuItem value={item} key={item}>{item}</MenuItem>
                  ))}
                </TextField>
              </Grid>
            </>
          )}
        </Grid>

        <Tabs
          value={tabIndex}
          onChange={handleTabChange}
          indicatorColor="primary"
          textColor="primary"
          sx={{ mb: 2 }}
        >
          {["File", "URL"].map((item, ind) => (
            <Tab key={ind} value={ind} label={item} sx={{ textTransform: "capitalize" }} />
          ))}
        </Tabs>

        {tabIndex === 0 && (
          <DropZone {...getRootProps()}>
            <input {...getInputProps()} />
            <Box display="flex" alignItems="center" flexDirection="column">
              <Publish sx={{ color: "text.secondary", fontSize: "48px" }} />
              {files.length ? <span>{files[0].name}</span> : <span>Drop file</span>}
            </Box>
          </DropZone>
        )}

        {tabIndex === 1 && (
          <TextField
            fullWidth size="small"
            InputLabelProps={{ shrink: true }}
            name="url" label="URL" variant="outlined"
            onChange={handleChange} value={state.url}
            sx={{ mb: 2 }}
          />
        )}

        <LoadingButton
          type="submit" color="primary" loading={loading}
          variant="contained" sx={{ px: 6 }}
        >
          Ingest
        </LoadingButton>
      </form>
    </Card>
  );
}
