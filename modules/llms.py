from app.llms.loader import localLoader
from app.llms.ollama import Ollama
from app.llms.qwen import QwenLLM
from app.llms.ollamamultimodal import OllamaMultiModal2
from llama_index.llms.openai import OpenAI

LLMS = {
    # "name": (LOADER, {"args": "here"}, "Prompt (check prompts.py)", "Privacy (public/private)", "Description...", "type (text/vision)", "Execution node", "chat/qa/both"),
  
    "openai_gpt3.5_turbo": (OpenAI, {"temperature": 0, "model": "gpt-3.5-turbo"}, "openai", "public", "OpenAI GPT-3.5 Turbo", "chat", "node1"),

    "openai_gpt4": (OpenAI, {"temperature": 0, "model": "gpt-4"}, "openai", "public", "OpenAI GPT-4 ", "chat", "node1"),

    "openai_gpt4_turbo": (OpenAI, {"temperature": 0, "model": "gpt-4-turbo-preview"}, "openai", "public", "OpenAI GPT-4 Turbo", "chat", "node1"),

    "mistral_7b": (Ollama, {"model": "mistral", "temperature": 0.0001, "keep_alive": 0}, "chatml", "private", "https://huggingface.co/TheBloke/Mistral-7B-OpenOrca-GPTQ", "chat", "node1"),

    "llama2_13b": (Ollama, {"model": "llama2:13b", "temperature": 0.0001, "keep_alive": 0}, "llama", "private", "https://huggingface.co/TheBloke/Llama-2-13B-chat-GPTQ", "chat", "node1"),

    "llama2_7b": (Ollama, {"model": "llama2:7b", "temperature": 0.0001, "keep_alive": 0}, "llama", "private", "https://huggingface.co/TheBloke/Llama-2-7B-Chat-GPTQ", "chat", "node1"),

    "llava16_13b": (OllamaMultiModal2, {"model": "llava:13b-v1.6", "temperature": 0.0001, "keep_alive": 0}, "llava", "private", "https://huggingface.co/llava-hf/llava-1.5-13b-hf", "vision", "node1"),

    "bakllava_7b": (OllamaMultiModal2, {"model": "bakllava", "temperature": 0.0001, "keep_alive": 0}, "llava", "private", "https://huggingface.co/llava-hf/bakLlava-v1-hf", "vision", "node1"),

    "mixtral_8x7b": (Ollama, {"model": "mixtral", "temperature": 0.1, "keep_alive": 0}, "mistral", "private", "https://huggingface.co/TheBloke/Mixtral-8x7B-Instruct-v0.1-GPTQ", "chat", "node2"),

    "llama2_70b": (Ollama, {"model": "llama2:70b", "temperature": 0.0001, "keep_alive": 0}, "llama", "private", "https://huggingface.co/TheBloke/Llama-2-70B-Chat-GPTQ", "chat", "node2"),

    "qwen_vl_chat": (QwenLLM, {"model": "Qwen/Qwen-VL-Chat"}, "plain", "private", "https://huggingface.co/Qwen/Qwen-VL-Chat", "vision", "node1"),

    #"spicyboros13b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Spicyboros-13B-2.2-GPTQ"}, "spicy", "private", "https://huggingface.co/TheBloke/Spicyboros-13B-2.2-GPTQ", "qa", "node1"),
}
