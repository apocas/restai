export const PROVIDER_CONFIG = {
  Ollama: {
    label: "Ollama",
    description: "Run open-source models locally with Ollama",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. llama3.1" },
      { name: "base_url", label: "Base URL", type: "text", required: false, placeholder: "http://localhost:11434", default: "" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0.1, step: 0.1 },
      { name: "keep_alive", label: "Keep Alive (seconds)", type: "number", required: false, default: 0 },
      { name: "request_timeout", label: "Request Timeout (seconds)", type: "number", required: false, default: 120 },
    ],
  },
  OllamaMultiModal: {
    label: "Ollama MultiModal",
    description: "Vision models via Ollama (LLaVA, etc.)",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. llava:13b" },
      { name: "base_url", label: "Base URL", type: "text", required: false, placeholder: "http://localhost:11434", default: "" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0.1, step: 0.1 },
      { name: "keep_alive", label: "Keep Alive (seconds)", type: "number", required: false, default: 0 },
      { name: "request_timeout", label: "Request Timeout (seconds)", type: "number", required: false, default: 120 },
    ],
  },
  OpenAI: {
    label: "OpenAI",
    description: "GPT-4o, GPT-4o Mini, and other OpenAI models",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. gpt-4o" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses OPENAI_API_KEY env var if empty" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
    ],
  },
  OpenAILike: {
    label: "OpenAI-Compatible",
    description: "Any provider with an OpenAI-compatible API",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. my-model" },
      { name: "api_base", label: "API Base URL", type: "text", required: true, placeholder: "https://api.example.com/v1" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "API key if required" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
      { name: "is_chat_model", label: "Is Chat Model", type: "boolean", required: false, default: true },
    ],
  },
  Groq: {
    label: "Groq",
    description: "Ultra-fast inference with Groq LPU",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. llama-3.1-70b-versatile" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses GROQ_API_KEY env var if empty" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
    ],
  },
  Anthropic: {
    label: "Anthropic",
    description: "Claude models from Anthropic",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. claude-sonnet-4-20250514" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses ANTHROPIC_API_KEY env var if empty" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
      { name: "max_tokens", label: "Max Tokens", type: "number", required: false, default: 4096 },
    ],
  },
  Grok: {
    label: "Grok (xAI)",
    description: "Grok models from xAI",
    fields: [
      { name: "model", label: "Model", type: "text", required: false, default: "grok-beta", placeholder: "e.g. grok-beta" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses XAI_API_KEY env var if empty" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
    ],
  },
  LiteLLM: {
    label: "LiteLLM",
    description: "Unified API proxy for 100+ LLM providers",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. openai/gpt-4o" },
      { name: "api_base", label: "API Base URL", type: "text", required: false, placeholder: "https://litellm.example.com" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "API key if required" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
    ],
  },
  vLLM: {
    label: "vLLM",
    description: "High-throughput serving with vLLM",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. meta-llama/Llama-3.1-8B" },
      { name: "api_url", label: "API URL", type: "text", required: true, placeholder: "http://localhost:8000" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
      { name: "max_tokens", label: "Max Tokens", type: "number", required: false, default: 4096 },
    ],
  },
  Gemini: {
    label: "Google Gemini",
    description: "Google Gemini text models",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. models/gemini-2.0-flash" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses GOOGLE_API_KEY env var if empty" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
    ],
  },
  GeminiMultiModal: {
    label: "Gemini MultiModal",
    description: "Google Gemini with vision capabilities",
    fields: [
      { name: "model", label: "Model", type: "text", required: true, placeholder: "e.g. models/gemini-2.0-flash" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses GOOGLE_API_KEY env var if empty" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
    ],
  },
  AzureOpenAI: {
    label: "Azure OpenAI",
    description: "OpenAI models hosted on Microsoft Azure",
    fields: [
      { name: "model", label: "Model / Deployment Name", type: "text", required: true, placeholder: "e.g. gpt-4o" },
      { name: "engine", label: "Engine (Deployment ID)", type: "text", required: true, placeholder: "e.g. my-gpt4o-deployment" },
      { name: "azure_endpoint", label: "Azure Endpoint", type: "text", required: true, placeholder: "https://my-resource.openai.azure.com/" },
      { name: "api_key", label: "API Key", type: "password", required: false, placeholder: "Uses AZURE_OPENAI_API_KEY env var if empty" },
      { name: "api_version", label: "API Version", type: "text", required: false, default: "2024-02-15-preview", placeholder: "e.g. 2024-02-15-preview" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
    ],
  },
  Bedrock: {
    label: "Amazon Bedrock",
    description: "Access Claude, Llama, Mistral, and more via AWS Bedrock",
    fields: [
      { name: "model", label: "Model ID", type: "text", required: true, placeholder: "e.g. anthropic.claude-3-sonnet-20240229-v1:0" },
      { name: "region_name", label: "AWS Region", type: "text", required: false, placeholder: "e.g. us-east-1", default: "us-east-1" },
      { name: "aws_access_key_id", label: "AWS Access Key ID", type: "password", required: false, placeholder: "Uses AWS_ACCESS_KEY_ID env var if empty" },
      { name: "aws_secret_access_key", label: "AWS Secret Access Key", type: "password", required: false, placeholder: "Uses AWS_SECRET_ACCESS_KEY env var if empty" },
      { name: "temperature", label: "Temperature", type: "number", required: false, default: 0, step: 0.1 },
      { name: "max_tokens", label: "Max Tokens", type: "number", required: false, default: 4096 },
    ],
  },
};
