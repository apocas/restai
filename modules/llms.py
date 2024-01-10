from langchain.llms import GPT4All, LlamaCpp, OpenAI
from langchain.chat_models import ChatOpenAI, ChatVertexAI
from app.llms.gemini import GeminiLLM
from app.llms.llava import LlavaLLM
from app.llms.loader import localLoader

LLMS = {
    # "name": (LOADER, {"args": "here"}, "Prompt (check prompts.py)", "Privacy (public/private)", "Description...", "type (text/vision)", "Execution node", "chat/qa/both"),

    # "llama2_7b_cpp": (LlamaCpp, {"temperature": 0, "model_path": "./models/llama-2-7b.Q4_K_M.gguf"}, "llama", "private", "Llamacpp", "qa", "node1"),
    "openai_gpt3.5": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-3.5-turbo"}, "openai", "public", "OpenAI GPT-3.5 Turbo", "chat", "node1"),
    "openai_gpt4": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4"}, "openai", "public", "OpenAI GPT-4 ", "chat", "node1"),
    "openai_gpt4_turbo": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4-1106-preview"}, "openai", "public", "OpenAI GPT-4 Turbo", "chat", "node1"),
    "google_vertexai_bison": (ChatVertexAI, {"model_name": "chat-bison@002", "max_output_tokens": 1000, "temperature": 0.1}, "openai", "public", "Google Vertex AI chat-bison@002", "qa", "node1"),
    "google_geminipro": (GeminiLLM, {"max_output_tokens": 2048, "temperature": 0.6, "top_p": 1}, "gemini", "public", "Google Gemini Pro", "chat", "node1"),
    # "llama13b_chat_gptq": (ChatOpenAI, {"temperature": 0.3, "openai_api_key": "na", "openai_api_base": "http://127.0.0.1:5000/v1"}, "llama", "private", "Llama 13B Chat GPTQ", "qa", "node1"),
    "mistral7b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Mistral-7B-OpenOrca-GPTQ"}, "openai", "private", "https://huggingface.co/TheBloke/Mistral-7B-OpenOrca-GPTQ", "qa", "node1"),
    "llama13b_chat_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Llama-2-13B-chat-GPTQ"}, "llama", "private", "https://huggingface.co/TheBloke/Llama-2-13B-chat-GPTQ", "qa", "node1"),
    "wizardlm13b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/WizardLM-13B-V1.2-GPTQ"}, "vicuna", "private", "https://huggingface.co/TheBloke/WizardLM-13B-V1.2-GPTQ", "qa", "node1"),
    "spicyboros13b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Spicyboros-13B-2.2-GPTQ"}, "spicy", "private", "https://huggingface.co/TheBloke/Spicyboros-13B-2.2-GPTQ", "qa", "node1"),
    "llava_1.5_13b": (LlavaLLM, {"model": "llava-hf/llava-1.5-13b-hf"}, "llava", "private", "https://huggingface.co/llava-hf/llava-1.5-13b-hf", "vision", "node1"),
    "bakllava_v1": (LlavaLLM, {"model": "llava-hf/bakLlava-v1-hf"}, "llava", "private", "https://huggingface.co/llava-hf/bakLlava-v1-hf", "vision", "node1"),
    "mixtral8x7b_instruct_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ", "temperature": 0.7}, "mistral", "private", "https://huggingface.co/TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ", "qa", "node2"),
    "llama2_70b_chat_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Llama-2-70B-Chat-GPTQ"}, "llama", "private", "https://huggingface.co/TheBloke/Llama-2-70B-Chat-GPTQ", "qa", "node2"),
}
