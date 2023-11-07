from langchain.llms import GPT4All, LlamaCpp, OpenAI
from langchain.chat_models import ChatOpenAI

LLMS = {
    "openai": (OpenAI, {"temperature": 0, "model_name": "text-davinci-003"}),
    "llama2_7b_cpp": (LlamaCpp, {"temperature": 0, "model_path": "./models/llama-2-7b.Q4_K_M.gguf"}),
    "gpt4all": (GPT4All, {"model": "./models/ggml-gpt4all-j-v1.3-groovy.bin", "backend": "gptj", "n_ctx": 1000}),
    "openai_gpt3.5": (ChatOpenAI, {"temperature": 0, "model_name":"gpt-3.5-turbo"}),
    "openai_gpt4": (ChatOpenAI, {"temperature": 0, "model_name":"gpt-4"}),
    "openai_gpt4_turbo": (ChatOpenAI, {"temperature": 0, "model_name":"gpt-4-1106-preview"}),
}