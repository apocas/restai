from app.llms.loader import localLoader
from app.llms.ollama import Ollama
from app.llms.qwen import QwenLLM
from app.llms.ollamamultimodal import OllamaMultiModal2
from llama_index.llms.openai import OpenAI

LLMS = {
    # "name": (LOADER, {"args": "here"}, "Prompt (check prompts.py)", "Privacy (public/private)", "Description...", "type (text/vision)", "Execution node", "chat/qa/both"),
  
    "openai_gpt3.5_turbo": (OpenAI, {"temperature": 0, "model": "gpt-3.5-turbo"}, None, "public", "OpenAI GPT-3.5 Turbo", "chat"),

    "openai_gpt4": (OpenAI, {"temperature": 0, "model": "gpt-4"}, None, "public", "OpenAI GPT-4 ", "chat"),

    "openai_gpt4_turbo": (OpenAI, {"temperature": 0, "model": "gpt-4-turbo-preview"}, None, "public", "OpenAI GPT-4 Turbo", "chat"),

    "mistral_7b": (Ollama, {"model": "mistral", "temperature": 0.0001, "keep_alive": 0}, None, "private", "https://ollama.com/library/mistral", "qa"),

    "llama2_13b": (Ollama, {"model": "llama2:13b", "temperature": 0.0001, "keep_alive": 0}, None, "private", "https://ollama.com/library/llama2", "chat"),

    "llama2_7b": (Ollama, {"model": "llama2:7b", "temperature": 0.0001, "keep_alive": 0}, None, "private", "https://ollama.com/library/llama2", "chat"),

    "llava16_13b": (OllamaMultiModal2, {"model": "llava:13b-v1.6", "temperature": 0.0001, "keep_alive": 0}, None, "private", "https://ollama.com/library/llava", "vision"),

    "bakllava_7b": (OllamaMultiModal2, {"model": "bakllava", "temperature": 0.0001, "keep_alive": 0}, None, "private", "https://ollama.com/library/bakllava", "vision"),

    "mixtral_8x7b": (Ollama, {"model": "mixtral", "temperature": 0.0001, "keep_alive": 0}, None, "private", "https://ollama.com/library/mixtral", "chat"),

    "llama2_70b": (Ollama, {"model": "llama2:70b", "temperature": 0.0001, "keep_alive": 0}, None, "private", "https://ollama.com/library/llama2", "chat"),

    "qwen_vl_chat": (QwenLLM, {"model": "Qwen/Qwen-VL-Chat"}, "plain", "private", "https://huggingface.co/Qwen/Qwen-VL-Chat", "vision"),

    #"spicyboros13b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Spicyboros-13B-2.2-GPTQ"}, "spicy", "private", "https://huggingface.co/TheBloke/Spicyboros-13B-2.2-GPTQ", "qa"),
}
