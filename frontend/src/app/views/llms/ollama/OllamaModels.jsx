import { useState, useEffect, useRef } from "react";
import {
  Grid,
  styled,
  Box,
  Card,
  TextField,
  Button,
  IconButton,
  Chip,
  Divider,
  Typography,
  CircularProgress,
  Tabs,
  Tab,
  Link
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { toast } from 'react-toastify';
import { H4 } from "app/components/Typography";
import api from "app/utils/api";
import SearchIcon from '@mui/icons-material/Search';
import AddCircleIcon from '@mui/icons-material/AddCircle';
import CloudDownloadIcon from '@mui/icons-material/CloudDownload';
import CloudIcon from '@mui/icons-material/Cloud';
import StorageIcon from '@mui/icons-material/Storage';
import ReactJson from '@microlink/react-json-view';
import MUIDataTable from "mui-datatables";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": { marginBottom: 30, [theme.breakpoints.down("sm")]: { marginBottom: 16 } }
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" }
}));

const OLLAMA_CLOUD_HOST = "https://ollama.com";

export default function OllamaModels() {
  const navigate = useNavigate();
  const auth = useAuth();
  // "local" connects to a self-hosted ollama daemon; "cloud" hits
  // ollama.com directly with a Bearer key — no daemon needed. Each mode
  // owns its own inputs and connection state so switching tabs doesn't
  // implicitly reuse the wrong credentials.
  const [mode, setMode] = useState("local");

  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState([]);
  const [connected, setConnected] = useState(false);

  // Local-instance state
  const [ollamaConfig, setOllamaConfig] = useState({
    host: "localhost",
    port: 11434
  });

  // Ollama Cloud state
  const [cloudApiKey, setCloudApiKey] = useState("");

  const [addingModel, setAddingModel] = useState(null);
  const [newModelName, setNewModelName] = useState("");
  const [pullingModel, setPullingModel] = useState(false);

  // The Add-to-System form renders below the (often long) model table —
  // without an explicit scroll the user clicks "Add" on a row at the top
  // of the table and sees nothing happen, because the new card opens
  // off-screen at the bottom. Scroll it into view when it appears.
  const addingModelRef = useRef(null);

  useEffect(() => {
    document.title = (process.env.REACT_APP_RESTAI_NAME || "RESTai") + ' - Import from Ollama';
  }, []);

  useEffect(() => {
    if (!addingModel) return;
    // Wait one tick so the card is mounted before we measure its position.
    const id = requestAnimationFrame(() => {
      addingModelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    return () => cancelAnimationFrame(id);
  }, [addingModel]);

  const handleInputChange = (e) => {
    const { name, value } = e.target;
    setOllamaConfig(prev => ({
      ...prev,
      [name]: value
    }));
  };

  const handleModeChange = (_e, newMode) => {
    if (newMode === null) return;
    setMode(newMode);
    // Switching modes invalidates the previous connection — different
    // backend, different credentials. Clear the model list so the operator
    // doesn't accidentally add a local model under cloud auth (or vice
    // versa) by clicking through stale results.
    setModels([]);
    setConnected(false);
    setAddingModel(null);
  };

  const fetchOllamaModels = async () => {
    setLoading(true);
    try {
      const data = await api.post("/tools/ollama/models", ollamaConfig, auth.user.token);
      setModels(data);
      setConnected(true);
      toast.success(`Found ${data.length} models on Ollama instance at ${ollamaConfig.host}:${ollamaConfig.port}`);
    } catch (error) {
      console.error('Error fetching Ollama models:', error);
      setModels([]);
      setConnected(false);
    } finally {
      setLoading(false);
    }
  };

  const fetchCloudModels = async () => {
    if (!cloudApiKey.trim()) {
      toast.error("Please paste your Ollama Cloud API key first");
      return;
    }
    setLoading(true);
    try {
      const data = await api.post(
        "/tools/ollama/cloud/models",
        { api_key: cloudApiKey.trim() },
        auth.user.token
      );
      setModels(data);
      setConnected(true);
      toast.success(`Found ${data.length} models on Ollama Cloud`);
    } catch (error) {
      console.error('Error fetching Ollama Cloud models:', error);
      setModels([]);
      setConnected(false);
    } finally {
      setLoading(false);
    }
  };

  const pullOllamaModel = async (modelName) => {
    try {
      toast.info(`Pulling model ${modelName}. This may take some time...`);

      await api.post("/tools/ollama/pull", {
        name: modelName,
        host: ollamaConfig.host,
        port: ollamaConfig.port
      }, auth.user.token);

      toast.success(`Successfully pulled model ${modelName}`);

      fetchOllamaModels();
    } catch (error) {
      console.error('Error pulling Ollama model:', error);
    }
  };

  const handlePullNewModel = async () => {
    if (!newModelName.trim()) {
      toast.error("Please enter a model name");
      return;
    }

    setPullingModel(true);
    try {
      await pullOllamaModel(newModelName.trim());
      setNewModelName("");
    } catch (error) {
      console.error("Error pulling new model:", error);
    } finally {
      setPullingModel(false);
    }
  };

  const handleAddModel = (model) => {
    setAddingModel(model);
  };

  // Cloud doesn't return capabilities/embedding_length on list (skipped
  // server-side to avoid one round-trip per model). Fall back to a name
  // heuristic so the form still picks the embedding flow when relevant.
  const isEmbeddingModel = (model) => {
    if (model?.capabilities?.includes("embedding")) return true;
    const n = (model?.name || "").toLowerCase();
    return n.includes("embed") || n.startsWith("nomic-embed") || n.startsWith("bge-");
  };

  const addModelToSystem = async () => {
    if (!addingModel) return;

    try {
      const isCloud = mode === "cloud";
      const baseUrl = isCloud
        ? OLLAMA_CLOUD_HOST
        : `http://${ollamaConfig.host}:${ollamaConfig.port}`;
      const sourceLabel = isCloud
        ? "Ollama Cloud"
        : `${ollamaConfig.host}:${ollamaConfig.port}`;

      if (isEmbeddingModel(addingModel)) {
        // Cloud embeddings aren't a thing today (Ollama Cloud only ships
        // LLMs), so block this path until/unless that changes — silently
        // POSTing an `OllamaEmbeddings` row pointing at ollama.com would
        // 401 on first inference and confuse the operator.
        if (isCloud) {
          toast.error("Ollama Cloud doesn't expose embedding models. Pick an LLM instead.");
          return;
        }
        const options = {
          model_name: addingModel.name,
          base_url: baseUrl,
          keep_alive: 0,
          mirostat: 0,
        };

        const embeddingData = {
          name: addingModel.name,
          class_name: "OllamaEmbeddings",
          options: JSON.stringify(options),
          dimension: addingModel.embedding_length || 1536,
          privacy: "private",
        };

        await api.post("/embeddings", embeddingData, auth.user.token);

        toast.success(`Successfully added embedding ${addingModel.name} to the system`);
        setAddingModel(null);
        navigate(`/embedding/${addingModel.name}`);
        return;
      }

      // LLM flow
      const options = {
        model: addingModel.name,
        temperature: 0.1,
        keep_alive: 0,
        request_timeout: 120,
        base_url: baseUrl,
      };
      // Cloud LLMs ride on a dedicated class (OllamaCloud) that wraps the
      // base Ollama provider with Bearer auth — no special-case branching
      // in the orchestrator. The api_key lives in LLM_SENSITIVE_KEYS so
      // it's encrypted at rest.
      if (isCloud) options.api_key = cloudApiKey.trim();

      const isMultiModal = addingModel.name.includes('llava') || addingModel.details?.families?.includes('clip');
      let className;
      if (isCloud) className = "OllamaCloud";
      else if (isMultiModal) className = "OllamaMultiModal2";
      else className = "Ollama";

      const modelData = {
        name: addingModel.name,
        class_name: className,
        options: JSON.stringify(options),
        privacy: "private",
        description: `Ollama model ${addingModel.name} from ${sourceLabel}`
      };

      await api.post("/llms", modelData, auth.user.token);

      toast.success(`Successfully added model ${addingModel.name} to the system`);
      setAddingModel(null);
    } catch (error) {
      console.error('Error adding model to the system:', error);
    }
  };

  const cancelAddModel = () => {
    setAddingModel(null);
  };

  const tableTitle = mode === "cloud" ? "Available Ollama Cloud Models" : "Available Ollama Models";

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb routeSegments={[
          { name: "LLMs", path: "/llms" },
          { name: "Import from Ollama", path: "/llms/ollama" }
        ]} />
      </Box>

      <ContentBox>
        <Grid container spacing={3}>
          <Grid item xs={12}>
            <Card elevation={3} sx={{ p: 3 }}>
              <Tabs
                value={mode}
                onChange={handleModeChange}
                sx={{ mb: 2, borderBottom: 1, borderColor: "divider" }}
              >
                <Tab
                  value="local"
                  icon={<StorageIcon fontSize="small" />}
                  iconPosition="start"
                  label="Local Instance"
                  sx={{ minHeight: 48, textTransform: "none" }}
                />
                <Tab
                  value="cloud"
                  icon={<CloudIcon fontSize="small" />}
                  iconPosition="start"
                  label="Ollama Cloud"
                  sx={{ minHeight: 48, textTransform: "none" }}
                />
              </Tabs>

              {mode === "local" ? (
                <>
                  <H4>Connect to Ollama Instance</H4>
                  <Divider sx={{ my: 2 }} />

                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <TextField
                      label="Host"
                      name="host"
                      value={ollamaConfig.host}
                      onChange={handleInputChange}
                      sx={{ mr: 2 }}
                    />
                    <TextField
                      label="Port"
                      name="port"
                      type="number"
                      value={ollamaConfig.port}
                      onChange={handleInputChange}
                      sx={{ mr: 2 }}
                    />
                    <Button
                      variant="contained"
                      startIcon={<SearchIcon />}
                      onClick={fetchOllamaModels}
                      disabled={loading}
                    >
                      {loading ? <CircularProgress size={24} /> : "Connect"}
                    </Button>
                  </Box>
                  <Typography variant="caption" color="textSecondary">
                    Connects to a self-hosted Ollama daemon (default: localhost:11434).
                  </Typography>
                </>
              ) : (
                <>
                  <H4>Connect to Ollama Cloud</H4>
                  <Divider sx={{ my: 2 }} />

                  <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                    <TextField
                      label="API Key"
                      type="password"
                      value={cloudApiKey}
                      onChange={(e) => setCloudApiKey(e.target.value)}
                      placeholder="ollama_..."
                      autoComplete="off"
                      fullWidth
                      sx={{ mr: 2 }}
                    />
                    <Button
                      variant="contained"
                      startIcon={<SearchIcon />}
                      onClick={fetchCloudModels}
                      disabled={loading || !cloudApiKey.trim()}
                    >
                      {loading ? <CircularProgress size={24} /> : "Connect"}
                    </Button>
                  </Box>
                  <Typography variant="caption" color="textSecondary">
                    No local install needed. Get a key at{" "}
                    <Link href="https://ollama.com/settings/keys" target="_blank" rel="noopener">
                      ollama.com/settings/keys
                    </Link>
                    . Cloud-only models are listed with a <code>:cloud</code> suffix
                    (e.g. <code>gpt-oss:120b-cloud</code>). Keys are encrypted at rest.
                  </Typography>
                </>
              )}
            </Card>
          </Grid>

          {/* Pull-new-model only applies to local — cloud catalog is server-side */}
          {connected && mode === "local" && (
            <Grid item xs={12}>
              <Card elevation={3} sx={{ p: 3 }}>
                <H4>Pull New Model</H4>
                <Divider sx={{ my: 2 }} />

                <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                  <TextField
                    fullWidth
                    label="Model Name (e.g., llama3, gemma, llava)"
                    value={newModelName}
                    onChange={(e) => setNewModelName(e.target.value)}
                    placeholder="Enter model name to pull"
                    helperText="Enter the name of a model you want to pull from Ollama's library"
                    sx={{ mr: 2 }}
                  />
                  <Button
                    variant="contained"
                    color="secondary"
                    startIcon={<CloudDownloadIcon />}
                    onClick={handlePullNewModel}
                    disabled={pullingModel || !newModelName.trim()}
                  >
                    {pullingModel ? <CircularProgress size={24} /> : "Pull Model"}
                  </Button>
                </Box>
                <Typography variant="caption" color="textSecondary">
                  Examples: llama3, llama3:8b, llava, gemma:7b, mistral, phi3:mini, deepseek:7b
                </Typography>
              </Card>
            </Grid>
          )}

          {models.length > 0 && (
            <Grid item xs={12}>
              <Card elevation={3} sx={{ pt: "20px", mb: 3 }}>
                <MUIDataTable
                  title={tableTitle}
                  data={models.map((model) => [
                    model.name,
                    isEmbeddingModel(model) ? "Embedding" : (model.details?.families?.includes('clip') ? "Vision" : "LLM"),
                    model.size ? `${(model.size / (1024 * 1024 * 1024)).toFixed(2)} GB` : 'Unknown',
                    model.modified_at ? new Date(model.modified_at).toLocaleDateString() : 'Unknown',
                    model.details?.families || [],
                    model
                  ])}
                  columns={[
                    {
                      name: "Name",
                      options: {
                        customBodyRender: (value) => <strong>{value}</strong>,
                        sort: true,
                        filter: true
                      }
                    },
                    {
                      name: "Type",
                      options: {
                        customBodyRender: (value) => (
                          <Chip
                            label={value}
                            size="small"
                            color={value === "Embedding" ? "secondary" : value === "Vision" ? "warning" : "primary"}
                          />
                        ),
                        sort: true,
                        filter: true
                      }
                    },
                    {
                      name: "Size",
                      options: {
                        sort: true,
                        filter: false
                      }
                    },
                    {
                      name: "Modified",
                      options: {
                        sort: true,
                        filter: false
                      }
                    },
                    {
                      name: "Details",
                      options: {
                        customBodyRender: (families) => (
                          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                            {families.map((family) => (
                              <Chip key={family} label={family} size="small" />
                            ))}
                          </Box>
                        ),
                        sort: false,
                        filter: false
                      }
                    },
                    {
                      name: "Actions",
                      options: {
                        customBodyRender: (model) => (
                          <Box display="flex" alignItems="center" gap={1}>
                            <IconButton color="primary" title="Add to System" onClick={() => handleAddModel(model)}>
                              <AddCircleIcon />
                            </IconButton>
                            {/* Pull/Update is local-only — cloud models live remotely */}
                            {mode === "local" && (
                              <IconButton color="secondary" title="Pull/Update Model" onClick={() => pullOllamaModel(model.name)}>
                                <CloudDownloadIcon />
                              </IconButton>
                            )}
                          </Box>
                        ),
                        sort: false,
                        filter: false
                      }
                    }
                  ]}
                  options={{
                    print: false,
                    selectableRows: "none",
                    download: false,
                    filter: true,
                    viewColumns: false,
                    rowsPerPage: 10,
                    rowsPerPageOptions: [10, 15, 100],
                    elevation: 0,
                    textLabels: {
                      body: {
                        noMatch: "No models found",
                        toolTip: "Sort",
                        columnHeaderTooltip: column => `Sort for ${column.label}`
                      },
                    },
                    sort: true
                  }}
                />
              </Card>
            </Grid>
          )}

          {connected && models.length === 0 && (
            <Grid item xs={12}>
              <Card elevation={3} sx={{ p: 3 }}>
                <Box sx={{ textAlign: 'center', py: 3 }}>
                  <Typography variant="h6" color="textSecondary" gutterBottom>
                    {mode === "cloud" ? "No models found on Ollama Cloud" : "No models found in Ollama instance"}
                  </Typography>
                  <Typography variant="body1" color="textSecondary">
                    {mode === "cloud"
                      ? "Your account may not have any models enabled — check the Ollama Cloud dashboard."
                      : "Use the \"Pull New Model\" section above to download your first model"}
                  </Typography>
                </Box>
              </Card>
            </Grid>
          )}

          {addingModel && (
            <Grid item xs={12} ref={addingModelRef}>
              <Card elevation={3} sx={{ p: 3 }}>
                <H4>Add Model to System</H4>
                <Divider sx={{ my: 2 }} />

                <Box sx={{ mb: 2 }}>
                  <Typography variant="subtitle1">
                    You are about to add the following model to the RESTai system:
                  </Typography>
                  <Typography variant="h6" sx={{ my: 1 }}>
                    {addingModel.name}
                    {" "}
                    <Chip
                      label={isEmbeddingModel(addingModel) ? "Embedding" : "LLM"}
                      size="small"
                      color={isEmbeddingModel(addingModel) ? "secondary" : "primary"}
                    />
                    {" "}
                    <Chip
                      label={mode === "cloud" ? "Cloud" : "Local"}
                      size="small"
                      icon={mode === "cloud" ? <CloudIcon /> : <StorageIcon />}
                      variant="outlined"
                    />
                  </Typography>

                  <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2">Model Details:</Typography>
                    {addingModel.details && Object.keys(addingModel.details).length > 0 && (
                      <Box sx={{ mt: 1, mb: 2 }}>
                        <ReactJson src={addingModel.details} collapsed={1} name={false} />
                      </Box>
                    )}
                  </Box>

                  <Box sx={{ mt: 3, display: 'flex', justifyContent: 'flex-end' }}>
                    <Button variant="outlined" onClick={cancelAddModel} sx={{ mr: 1 }}>
                      Cancel
                    </Button>
                    <Button variant="contained" color="primary" onClick={addModelToSystem}>
                      Add Model to System
                    </Button>
                  </Box>
                </Box>
              </Card>
            </Grid>
          )}
        </Grid>
      </ContentBox>
    </Container>
  );
}
