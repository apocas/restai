from langchain.llms import GPT4All, LlamaCpp, OpenAI
from langchain.chat_models import ChatOpenAI
from app.loader import localLoader

LLMS = {
    "openai": (OpenAI, {"temperature": 0, "model_name": "text-davinci-003"}, "chatml", "public"),
    # "llama2_7b_cpp": (LlamaCpp, {"temperature": 0, "model_path": "./models/llama-2-7b.Q4_K_M.gguf"}, "llama"),
    "openai_gpt3.5": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-3.5-turbo"}, "chatml", "public"),
    "openai_gpt4": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4"}, "chatml", "public"),
    "openai_gpt4_turbo": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4-1106-preview"}, "chatml", "public"),
    "llama13b_chat_gptq": (ChatOpenAI, {"temperature": 0.3, "openai_api_key": "na", "openai_api_base": "http://127.0.0.1:5000/v1"}, "llama", "private"),
    "mistral7b_gptq": (localLoader, {"type": "gptq", "model": "TheBloke/Mistral-7B-OpenOrca-GPTQ"}, "chatml", "private"),
}
