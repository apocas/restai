export const EMBEDDING_PROVIDER_CONFIG = {
  LangChain: {
    label: "OpenAI Embeddings",
    description: "OpenAI embedding models via LangChain",
    defaultDimension: 1536,
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. text-embedding-3-small" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses OPENAI_API_KEY env var if empty" },
    ],
  },
  "LangChain.HuggingFace": {
    label: "HuggingFace Embeddings",
    description: "Local or HuggingFace Hub embedding models",
    defaultDimension: 768,
    fields: [
      { name: "model_name", label: "Model Name", type: "text", required: true, placeholder: "e.g. BAAI/bge-small-en-v1.5" },
    ],
  },
  Ollama: {
    label: "Ollama Embeddings",
    description: "Run embedding models locally with Ollama",
    defaultDimension: 1024,
    fields: [
      { name: "model_name", label: "Model Name", type: "text", required: true, placeholder: "e.g. nomic-embed-text" },
      { name: "base_url", label: "Base URL", type: "text", required: false, placeholder: "http://localhost:11434", default: "" },
    ],
  },
};
