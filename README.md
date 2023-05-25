# restai

RESTAI is a simple generic REST API that allows to create embeddings for a lot of data types and then interact with them using a LLM.
This LLM may be an OpenAI based model, llamacpp, gpt4all or any other LLM supported by langchain.

## Details
### Embeddings
* Create embeddings from your data. You are able to ingest data by uploading files ou directly parsing URLs.
* You may [pick whatever](modules/embeddings.py) embeddings model thats supported by langchain, cloud based (ex: Openai) or private (HuggingFace model).

### Loaders
* You may use [any loader](modules/loaders.py) supported by langchain.

### LLMs
* You may use [any LLM](modules/llms.py) supported by langchain.
* There are two main ways to interact with the LLM: QA(questions and answers) and text generation aKa chat.

## Usage

## Endpoints
### Project
* GET "/projects"
* POST "/projects"
* DELETE "/projects/{projectName}"
* GET "/projects/{projectName}"
### Embeddings
* POST "/projects/{projectName}/ingest/url"
* POST "/projects/{projectName}/ingest/upload"
### LLMs
* POST "/projects/{projectName}/question"
* POST "/projects/{projectName}/chat"
