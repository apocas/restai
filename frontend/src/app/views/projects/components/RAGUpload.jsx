import { useEffect, useState } from "react";
import { Card, Divider, Grid, MenuItem, styled, TextField, Tabs, Tab } from "@mui/material";
import Publish from "@mui/icons-material/Publish";
import { useDropzone } from "react-dropzone";
import { toast } from 'react-toastify';
import { H4 } from "app/components/Typography";
import useAuth from "app/hooks/useAuth";
import { FlexAlignCenter, FlexBox } from "app/components/FlexBox";
import { FileUpload } from "@mui/icons-material";
import { convertHexToRGB } from "app/utils/utils";
import { LoadingButton } from "@mui/lab";
import { use } from "react";

const Form = styled("form")({
  paddingLeft: "16px",
  paddingRight: "16px"
});

const DropZone = styled(FlexAlignCenter)(({ isDragActive, theme }) => ({
  height: 160,
  width: "100%",
  cursor: "pointer",
  borderRadius: "4px",
  marginBottom: "16px",
  transition: "all 350ms ease-in-out",
  border: `2px dashed rgba(${convertHexToRGB(theme.palette.text.primary)}, 0.3)`,
  "&:hover": {
    background: `rgb(${convertHexToRGB(theme.palette.text.primary)}, 0.2) !important`
  },
  background: isDragActive ? "rgb(0, 0, 0, 0.15)" : "rgb(0, 0, 0, 0.01)"
}));

export default function RAGUpload({ project }) {
  const url = process.env.REACT_APP_RESTAI_API_URL || "";
  const auth = useAuth();
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [state, setState] = useState({ "chunksize": "512", "splitter": "token" });
  const { getRootProps, getInputProps, acceptedFiles } = useDropzone({
    "maxFiles": 1,
    "multiple": false
  });
  const [tabIndex, setTabIndex] = useState(0);
  const [tabIndex2, setTabIndex2] = useState(0);
  const handleTabChange = (e, value) => setTabIndex(value);
  const handleTabChange2 = (e, value) => setTabIndex2(value);


  const handleSubmit = async (event) => {
    event.preventDefault();

    setLoading(true);

    if (tabIndex === 0) {
      const formData = new FormData();
      formData.append("file", files[0]);

      if (tabIndex2 === 1) {
        formData.append("classic", "true");
        formData.append("splitter", state.splitter);
        formData.append("chunks", state.chunksize);
      }

      try {
        const response = await fetch(url + "/projects/" + project.id + "/embeddings/ingest/upload", {
          method: 'POST',
          headers: new Headers({ 'Authorization': 'Basic ' + auth.user.token }),
          body: formData,
        });
    
        const data = await response.json();
        if (!response.ok) {
          toast.error(data.detail);
          toast.warning("Retry in classic mode if the error persists.");
          //throw new Error(response.statusText);
        } else {
          window.location.reload();
        }
      } catch (err) {
        toast.error(err.toString());
      } finally {
        setLoading(false);
      }
    } else if (tabIndex === 1) {
      var body = {
        "url": state.url,
        "splitter": state.splitter,
        "chunks": state.chunksize
      }

      try {
        const response = await fetch(url + "/projects/" + project.id + "/embeddings/ingest/url", {
          method: 'POST',
          headers: new Headers({ 'Content-Type': 'application/json', 'Authorization': 'Basic ' + auth.user.token }),
          body: JSON.stringify(body),
        });
    
        const data = await response.json();
        if (!response.ok) {
          toast.error(data.detail);
          //throw new Error(response.statusText);
        } else {
          window.location.reload();
        }        
      } catch (err) {
        toast.error(err.toString());
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

  useEffect(() => {
    if (tabIndex === 1) {
      setTabIndex2(1);
    }
  }, [tabIndex]);

  return (
    <Card elevation={3}>
      <FlexBox>
        <FileUpload sx={{ ml: 2, mt: 2 }} />
        <H4 sx={{ p: 2 }}>
          Ingest data
        </H4>
      </FlexBox>

      <Divider />

      <Form onSubmit={handleSubmit}>
        <Grid container spacing={3} sx={{ mt: 0 }}>
          <Grid item sm={12} xs={12}>
            <Tabs
              value={tabIndex2}
              onChange={handleTabChange2}
              indicatorColor="primary"
              textColor="primary">
              {["Docling", "Classic"].map((item, ind) => (
                <Tab key={ind} value={ind} label={item} sx={{ textTransform: "capitalize" }} />
              ))}
            </Tabs>

            <Divider sx={{ mb: "24px" }} />

            {tabIndex2 === 1 && <>
              <TextField
                fullWidth
                select
                name="splitter"
                label="Splitter"
                variant="outlined"
                onChange={handleChange}
                value={state.splitter}
                defaultValue={state.splitter}
                sx={{ mb: 2 }}
              >
                {["token", "sentence"].map((item, ind) => (
                  <MenuItem value={item} key={item}>
                    {item}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                fullWidth
                select
                name="chunksize"
                label="Chunk Size"
                variant="outlined"
                onChange={handleChange}
                value={state.chunksize}
                defaultValue={state.chunksize}
                sx={{ mb: 2 }}
              >
                {["126", "256", "512", "1024", "2048"].map((item, ind) => (
                  <MenuItem value={item} key={item}>
                    {item}
                  </MenuItem>
                ))}
              </TextField>
            </>}

            <Tabs
              value={tabIndex}
              onChange={handleTabChange}
              indicatorColor="primary"
              textColor="primary">
              {["File", "URL"].map((item, ind) => (
                <Tab key={ind} value={ind} label={item} sx={{ textTransform: "capitalize" }} />
              ))}
            </Tabs>

            <Divider sx={{ mb: "24px" }} />

            {tabIndex === 0 &&
              <DropZone {...getRootProps()}>
                <input {...getInputProps()} />
                <FlexBox alignItems="center" flexDirection="column">
                  <Publish sx={{ color: "text.secondary", fontSize: "48px" }} />
                  {files.length ? (
                    <span>{files[0].name}</span>
                  ) : (
                    <span>Drop file</span>
                  )}
                </FlexBox>
              </DropZone>
            }

            {tabIndex === 1 && <>
              <TextField
                fullWidth
                InputLabelProps={{ shrink: true }}
                name="url"
                label="URL"
                variant="outlined"
                onChange={handleChange}
                value={state.url}
                sx={{ mb: "24px" }}
              /></>}
          </Grid>
        </Grid>

        <LoadingButton
          type="submit"
          color="primary"
          loading={loading}
          variant="contained"
          sx={{ mb: 2, px: 6 }}>
          Ingest
        </LoadingButton>
      </Form>
    </Card>
  );
}

