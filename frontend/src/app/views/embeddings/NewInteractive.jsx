import { useState, useEffect } from "react";
import {
  Grid,
  styled,
  Box,
  Card,
  TextField,
  Button,
  MenuItem,
  Divider,
  Typography,
} from "@mui/material";
import useAuth from "app/hooks/useAuth";
import Breadcrumb from "app/components/Breadcrumb";
import { useNavigate } from "react-router-dom";
import { toast } from "react-toastify";
import { H4 } from "app/components/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ReactJson from "@microlink/react-json-view";
import { EMBEDDING_PROVIDER_CONFIG } from "./embeddingProviderConfig";
import api from "app/utils/api";

const Container = styled("div")(({ theme }) => ({
  margin: 10,
  [theme.breakpoints.down("sm")]: { margin: 16 },
  "& .breadcrumb": {
    marginBottom: 30,
    [theme.breakpoints.down("sm")]: { marginBottom: 16 },
  },
}));

const ContentBox = styled("div")(({ theme }) => ({
  margin: "30px",
  [theme.breakpoints.down("sm")]: { margin: "16px" },
}));

const ProviderCard = styled(Card)(({ theme }) => ({
  padding: theme.spacing(2.5),
  cursor: "pointer",
  transition: "all 0.2s ease",
  height: "100%",
  display: "flex",
  flexDirection: "column",
  justifyContent: "center",
  "&:hover": {
    transform: "translateY(-3px)",
    boxShadow: theme.shadows[8],
  },
}));

export default function NewInteractive() {
  const auth = useAuth();
  const navigate = useNavigate();

  const [selectedProvider, setSelectedProvider] = useState(null);
  const [formState, setFormState] = useState({
    name: "",
    privacy: "private",
    description: "",
    dimension: 1536,
  });
  const [optionsState, setOptionsState] = useState({});

  useEffect(() => {
    document.title =
      (process.env.REACT_APP_RESTAI_NAME || "RESTai") + " - New Embedding";
  }, []);

  const handleSelectProvider = (providerKey) => {
    const provider = EMBEDDING_PROVIDER_CONFIG[providerKey];
    setSelectedProvider(providerKey);

    // Initialize options with defaults
    const defaults = {};
    provider.fields.forEach((field) => {
      if (field.default !== undefined && field.default !== "") {
        defaults[field.name] = field.default;
      }
    });
    setOptionsState(defaults);
    setFormState((prev) => ({ ...prev, dimension: provider.defaultDimension }));
  };

  const handleBack = () => {
    setSelectedProvider(null);
    setOptionsState({});
    setFormState({ name: "", privacy: "private", description: "", dimension: 1536 });
  };

  const handleFormChange = (e) => {
    const { name, value } = e.target;
    setFormState((prev) => ({ ...prev, [name]: value }));
  };

  const handleOptionChange = (fieldName, value) => {
    setOptionsState((prev) => ({ ...prev, [fieldName]: value }));
  };

  const handleJsonUpdate = (update) => {
    setOptionsState(update.updated_src);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!formState.name.trim()) {
      toast.error("Name is required");
      return;
    }

    // Build options, omitting empty strings
    const options = {};
    Object.entries(optionsState).forEach(([key, value]) => {
      if (value !== "" && value !== undefined) {
        options[key] = value;
      }
    });

    try {
      const data = await api.post("/embeddings", {
        name: formState.name,
        class_name: selectedProvider,
        options: JSON.stringify(options),
        privacy: formState.privacy,
        description: formState.description,
        dimension: Number(formState.dimension),
      }, auth.user.token);

      navigate("/embedding/" + data.name);
    } catch (err) {
      // error auto-toasted
    }
  };

  const renderField = (field) => {
    const value = optionsState[field.name] ?? field.default ?? "";

    return (
      <Grid item xs={12} sm={6} key={field.name}>
        <TextField
          fullWidth
          size="small"
          label={field.label}
          type={field.type === "password" ? "password" : field.type === "number" ? "number" : "text"}
          required={field.required}
          value={value}
          placeholder={field.placeholder || ""}
          inputProps={field.type === "number" ? { step: field.step || 1 } : {}}
          onChange={(e) => {
            const val =
              field.type === "number"
                ? e.target.value === "" ? "" : Number(e.target.value)
                : e.target.value;
            handleOptionChange(field.name, val);
          }}
        />
      </Grid>
    );
  };

  // Phase 1: Provider selection grid
  if (!selectedProvider) {
    return (
      <Container>
        <Box className="breadcrumb">
          <Breadcrumb
            routeSegments={[
              { name: "Embeddings", path: "/embeddings" },
              { name: "New Embedding", path: "/embeddings/new" },
            ]}
          />
        </Box>

        <ContentBox>
          <H4 sx={{ mb: 3 }}>Select an Embedding Provider</H4>
          <Grid container spacing={2}>
            {Object.entries(EMBEDDING_PROVIDER_CONFIG).map(([key, provider]) => (
              <Grid item xs={12} sm={6} md={4} lg={3} key={key}>
                <ProviderCard
                  elevation={3}
                  onClick={() => handleSelectProvider(key)}
                >
                  <Typography variant="h6" gutterBottom>
                    {provider.label}
                  </Typography>
                  <Typography variant="body2" color="textSecondary">
                    {provider.description}
                  </Typography>
                </ProviderCard>
              </Grid>
            ))}
          </Grid>
        </ContentBox>
      </Container>
    );
  }

  // Phase 2: Configuration form
  const provider = EMBEDDING_PROVIDER_CONFIG[selectedProvider];

  return (
    <Container>
      <Box className="breadcrumb">
        <Breadcrumb
          routeSegments={[
            { name: "Embeddings", path: "/embeddings" },
            { name: "New Embedding", path: "/embeddings/new" },
            { name: provider.label },
          ]}
        />
      </Box>

      <ContentBox>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={handleBack}
          sx={{ mb: 2 }}
        >
          Back to Providers
        </Button>

        <Card elevation={3} sx={{ p: 3 }}>
          <H4>New {provider.label}</H4>
          <Divider sx={{ my: 2 }} />

          <form onSubmit={handleSubmit}>
            <Grid container spacing={3}>
              {/* Common fields */}
              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  label="Class"
                  value={selectedProvider}
                  InputProps={{ readOnly: true }}
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  required
                  size="small"
                  name="name"
                  label="Name"
                  value={formState.name}
                  onChange={handleFormChange}
                  placeholder="Unique name for this embedding"
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  select
                  size="small"
                  name="privacy"
                  label="Privacy"
                  value={formState.privacy}
                  onChange={handleFormChange}
                >
                  {["public", "private"].map((p) => (
                    <MenuItem key={p} value={p}>
                      {p}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  name="dimension"
                  label="Dimension"
                  type="number"
                  value={formState.dimension}
                  onChange={(e) =>
                    setFormState((prev) => ({
                      ...prev,
                      dimension: e.target.value === "" ? "" : Number(e.target.value),
                    }))
                  }
                />
              </Grid>

              <Grid item xs={12} sm={6}>
                <TextField
                  fullWidth
                  size="small"
                  name="description"
                  label="Description"
                  value={formState.description}
                  onChange={handleFormChange}
                />
              </Grid>

              {/* Provider-specific fields */}
              <Grid item xs={12}>
                <Divider sx={{ my: 1 }} />
                <Typography variant="subtitle2" sx={{ mt: 1, mb: 1 }}>
                  {provider.label} Options
                </Typography>
              </Grid>

              {provider.fields.map(renderField)}

              {/* Live JSON viewer/editor */}
              <Grid item xs={12}>
                <Divider sx={{ my: 1 }} />
                <Typography variant="subtitle2" sx={{ mt: 1, mb: 1 }}>
                  Options JSON
                </Typography>
                <Typography variant="caption" color="textSecondary" sx={{ mb: 1, display: "block" }}>
                  Auto-updated from the fields above. Click values to edit, or use +/- to add/remove custom options.
                </Typography>
                <ReactJson
                  src={optionsState}
                  name={false}
                  enableClipboard={true}
                  onEdit={handleJsonUpdate}
                  onAdd={handleJsonUpdate}
                  onDelete={handleJsonUpdate}
                  displayDataTypes={false}
                  displayObjectSize={false}
                />
              </Grid>
            </Grid>

            <Box mt={3}>
              <Button color="primary" variant="contained" type="submit">
                Create Embedding
              </Button>
            </Box>
          </form>
        </Card>
      </ContentBox>
    </Container>
  );
}
