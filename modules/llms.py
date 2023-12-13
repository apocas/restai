from langchain.llms import GPT4All, LlamaCpp, OpenAI
from langchain.chat_models import ChatOpenAI, ChatVertexAI
from app.loader import localLoader

LLMS = {
    "openai": (OpenAI, {"temperature": 0, "model_name": "text-davinci-003"}, "chatml", "public", "OpenAI Davinci"),
    # "llama2_7b_cpp": (LlamaCpp, {"temperature": 0, "model_path": "./models/llama-2-7b.Q4_K_M.gguf"}, "llama"),
    "openai_gpt3.5": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-3.5-turbo"}, "chatml", "public", "OpenAI GPT-3.5 Turbo"),
    "openai_gpt4": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4"}, "chatml", "public", "OpenAI GPT-4 "),
    "openai_gpt4_turbo": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4-1106-preview"}, "chatml", "public", "OpenAI GPT-4 Turbo"),
    "google_vertexai_bison": (ChatVertexAI, {"model_name": "chat-bison@002", "max_output_tokens":1000, "temperature":0.1}, "chatml", "public", "Google Vertex AI chat-bison@002"),
    #"llama13b_chat_gptq": (ChatOpenAI, {"temperature": 0.3, "openai_api_key": "na", "openai_api_base": "http://127.0.0.1:5000/v1"}, "llama", "private", "Llama 13B Chat GPTQ"),
    "mistral7b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Mistral-7B-OpenOrca-GPTQ"}, "chatml", "private", "https://huggingface.co/TheBloke/Mistral-7B-OpenOrca-GPTQ"),
    "llama13b_chat_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Llama-2-13B-chat-GPTQ"}, "llama", "private", "https://huggingface.co/TheBloke/Llama-2-13B-chat-GPTQ"),
    "wizardlm13b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/WizardLM-13B-V1.2-GPTQ"}, "vicuna", "private", "https://huggingface.co/TheBloke/WizardLM-13B-V1.2-GPTQ"),
    "spicyboros13b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Spicyboros-13B-2.2-GPTQ"}, "spicy", "private", "https://huggingface.co/TheBloke/Spicyboros-13B-2.2-GPTQ"),
    
}
