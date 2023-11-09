from langchain.llms import GPT4All, LlamaCpp, OpenAI
from langchain.chat_models import ChatOpenAI

LLMS = {
    "openai": (OpenAI, {"temperature": 0, "model_name": "text-davinci-003"}),
    # "llama2_7b_cpp": (LlamaCpp, {"temperature": 0, "model_path": "./models/llama-2-7b.Q4_K_M.gguf"}),
    "openai_gpt3.5": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-3.5-turbo"}),
    "openai_gpt4": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4"}),
    "openai_gpt4_turbo": (ChatOpenAI, {"temperature": 0, "model_name": "gpt-4-1106-preview"}),
    "llama13b_chat_gptq": (ChatOpenAI, {"temperature": 0.5, "openai_api_key": "na", "openai_api_base": "http://127.0.0.1:5000/v1"}),
}
