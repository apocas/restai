from langchain import LLMChain, OpenAI, PromptTemplate
from langchain.llms import GPT4All, LlamaCpp
from langchain.chat_models import ChatOpenAI

LLMS = {
    "openai": (OpenAI, {"temperature": 0, "model_name": "text-davinci-003"}),
    "llamacpp": (LlamaCpp, {"model": "./models/ggml-model-q4_0.bin"}),
    "gpt4all": (GPT4All, {"model": "./models/ggml-gpt4all-j-v1.3-groovy.bin", "backend": "gptj", "n_ctx": 1000}),
    "chat": (ChatOpenAI, {"temperature": 0, "model_name":"gpt-3.5-turbo"}),
    "chat4": (ChatOpenAI, {"temperature": 0, "model_name":"gpt-4"}),
}