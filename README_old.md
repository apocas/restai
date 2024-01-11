# restai

* RESTAI is a generic REST API that allows to create embeddings from multiple datatypes and then interact with them using a LLM. An API for the RAG process.
* This LLM may be an OpenAI based model, llamacpp, transformer or any other LLM supported by langchain or compatible with OpenAI API.
* If you want to be completely offline, you may use (for example) the `llama13b_chat_gptq` LLM and `all-mpnet-base-v2` embeddings.
* RESTAI features an abstraction layer supporting multiple vectorstores, right now Chroma and Redis is supported.
* It was built thinking on low vram enviromnents, it loads and unloads LLMs automatically allowing to use multiple LLMs even if they don't all fit in VRAM simultaneously.
## Details
### Embeddings
* Create embeddings from your data. You are able to ingest data by uploading files ou directly parsing an URL content.
* You may [pick whatever](modules/embeddings.py) embeddings model thats supported by langchain, cloud based (ex: Openai) or private (HuggingFace model).
* You can easily manage embeddings per project, view, delete and ingest new data.

### Loaders
* You may use [any loader](modules/loaders.py) supported by llamaindex.

### LLMs
* You may use [any LLM](modules/llms.py) supported by langchain and/or transformers pipes.
* You may declare [PROMPTs](modules/prompts.py) templates and then use these prompts in the [LLMs](modules/llms.py).

## Default support

* Embeddings: `all-mpnet-base-v2` (HuggingFace), `openai` (OpenAI), ...
* LLM: `mixtral8x7b_instruct_gptq` (Transformers Pipeline), `openai` (OpenAI, text-generation-webui), ...
* It's very easy to add support for more [embeddings](modules/embeddings.py), [loaders](modules/loaders.py) and [LLMs](modules/llms.py).

## Installation

* RestAI uses [Poetry](https://python-poetry.org/) to manage dependencies. Install it with `pip install poetry`.

### Development
* make install
* make dev (starts restai in development mode)
* make devfrontend (starts restai's frontend in development mode)

### Production
* make install
* make prod

## Endpoints [(Swagger)](https://apocas.github.io/restai/):

### Users

* A user represents a user of the system.
* It's used for authentication and authorization. (basic auth)
* Each user may have access to multiple projects.

### Projects

---

* A project is an abstract entity basically a tenant. You may have multiple projects and each project has its own embeddings, loaders and llms.
* Each project may have multiple users with access to it.
* Projects have "sandboxed" mode, which means that a locked default answer will be given when there aren't embeddings for the provided question. This is useful for chatbots, where you want to provide a default answer when the LLM doesn't know how to answer the question, reduncing hallucination.


### Embeddings



### LLMs



## [All endpoints (Swagger)](https://apocas.github.io/restai/)

## Frontend

* There is a frontend available at [https://github.com/apocas/restai-frontend](https://github.com/apocas/restai-frontend).
* `make install` also installs the frontend.

## Tests

 * Tests are implemented using `pytest`. Run them with `make test`.
 * Running on a Macmini M1 8gb takes around 5~10mins to run the HuggingFace tests. Which uses an local LLM and a local embeddings model from HuggingFace.

## License

Pedro Dias - [@pedromdias](https://twitter.com/pedromdias)

Licensed under the Apache license, version 2.0 (the "license"); You may not use this file except in compliance with the license. You may obtain a copy of the license at:

    http://www.apache.org/licenses/LICENSE-2.0.html

Unless required by applicable law or agreed to in writing, software distributed under the license is distributed on an "as is" basis, without warranties or conditions of any kind, either express or implied. See the license for the specific language governing permissions and limitations under the license.
