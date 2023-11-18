# restai

* RESTAI is a simple generic REST API that allows to create embeddings from multiple datatypes and then interact with them using a LLM.
* This LLM may be an OpenAI based model, llamacpp, gpt4all or any other LLM supported by langchain.
* If you want to be completely offline, you may use (for example) the `gpt4all` LLM and `huggingface` embeddings.
## Details
### Embeddings
* Create embeddings from your data. You are able to ingest data by uploading files ou directly parsing an URL content.
* You may [pick whatever](modules/embeddings.py) embeddings model thats supported by langchain, cloud based (ex: Openai) or private (HuggingFace model).

### Loaders
* You may use [any loader](modules/loaders.py) supported by langchain.

### LLMs
* You may use [any LLM](modules/llms.py) supported by langchain.
* There are two main ways to interact with the LLM: QA(questions and answers) and text generation aKa chat.

## Default support

* Embeddings: `huggingface` (HuggingFace), `openai` (OpenAI), ...
* LLM: `llamacpp` (ggml-model-q4_0.bin), `openai` (OpenAI, text-generation-webui), ...
* It's very easy to add support for more [embeddings](modules/embeddings.py), [loaders](modules/loaders.py) and [LLMs](modules/llms.py).

## Example usage

**POST /projects ({"name": "test_openai",  "embeddings": "openai", "llm": "openai"})**
```json 
{"project": "test_openai"}
```

**POST /projects/test_openai/ingest/upload (upload a [test.txt](tests/test.txt))**
```json 
{"project": "test_openai", "embeddings": "openai", "documents": 2}
```

**POST /projects/test_openai/question ({"question": "What is the secret?"})**
```json 
{"question": "What is the secret?", "answer": "The secret is that ingenuity should be bigger than politics and corporate greed."}
```

**POST /projects/test_openai/question ({"system": "You are a digital assistant, answer only in french.", "question": "What is the secret?"})**
```json 
{"question": "What is the secret?", "answer": "Le secret est que l'ingéniosité doit être plus grande que la politique et la cupidité des entreprises."}
```

## Endpoints [(Swagger)](https://apocas.github.io/restai/):

### Users

A user represents a user of the system. It's used for authentication and authorization. Each user may have access to multiple projects.

[**GET /users**](https://apocas.github.io/restai/#/default/read_users_users_get)

- Description: Lists all users.

[**POST /users**](https://apocas.github.io/restai/#/default/create_user_users_post)

- Description: Create a user.

[**GET /users/{username}**](https://apocas.github.io/restai/#/default/get_user_users__username__get)

- Description: Get a specific user details.


[**DELETE /users/{username}**](https://apocas.github.io/restai/#/default/delete_user_users__username__delete)

- Description: Delete a user

[**PATCH /users/{username}**](https://apocas.github.io/restai/#/default/update_user_users__username__patch)

- Description: Edit a user

### Projects

---

A project is an abstract entity basically a tenant. You may have multiple projects and each project has its own embeddings, loaders and llms. Each project may have multiple users with access to it.

[**GET /projects**](https://apocas.github.io/restai/#/projects/get_projects)

- Description: Lists all the projects.

[**GET /projects/{projectName}**](https://apocas.github.io/restai/#/default/get_project_projects__projectName__get)

- Description: Get the specific project details.

[**DELETE /projects/{projectName}**](https://apocas.github.io/restai/#/default/delete_project_projects__projectName__delete)

- Description: Deletes the specific project.

[**POST /projects**](https://apocas.github.io/restai/#/default/create_project_projects_post)

- Description: Creates a new project.

[**PATCH /projects/{projectName}**](https://apocas.github.io/restai/#/default/edit_project_projects__projectName__patch)

- Description: Edit a project

### Embeddings - main endpoints

---

[**POST /projects/{projectName}/embeddings/ingest/url**](https://apocas.github.io/restai/#/default/ingest_url_projects__projectName__embeddings_ingest_url_post)

- Description: Ingests data into a specific project from a provided URL.

[**POST /projects/{projectName}/embeddings/ingest/upload**](https://apocas.github.io/restai/#/default/ingest_file_projects__projectName__embeddings_ingest_upload_post)

[**GET /projects/{projectName}/embeddings/urls**](https://apocas.github.io/restai/#/default/list_urls_projects__projectName__embeddings_urls_get)
- Description: Lists all the ingested URLs from a specific project.

[**GET /projects/{projectName}/embeddings/files**](https://apocas.github.io/restai/#/default/list_files_projects__projectName__embeddings_files_get)
- Description: Lists all the ingested files from a specific project.

[**DELETE /projects/{projectName}/embeddings/{id}**](https://apocas.github.io/restai/#/default/delete_embedding_projects__projectName__embeddings__id__delete)

- Description: Deletes a specific embedding from a specific project.

[**DELETE /projects/{projectName}/embeddings/url/{url}**](https://apocas.github.io/restai/#/default/delete_url_projects__projectName__embeddings_url__url__delete)

- Description: Deletes a specific embedding from a specific project. Providing a previously ingested URL.

[**DELETE /projects/{projectName}/embeddings/files/{fileName}**](https://apocas.github.io/restai/#/default/delete_file_projects__projectName__embeddings_files__fileName__delete)

- Description: Deletes a specific embedding from a specific project. Providing a previously ingested filename.

### LLMs

---

[**POST /projects/{projectName}/question**](https://apocas.github.io/restai/#/default/question_project_projects__projectName__question_post)

- Description: Asks a question to a specific project.

[**POST /projects/{projectName}/chat**](https://apocas.github.io/restai/#/default/chat_project_projects__projectName__chat_post)

- Description: Send a chat message to a specific project. Chat differs from question, because it holds conversation history. It's chat has an unique ID (id field).

## [All endpoints (Swagger)](https://apocas.github.io/restai/)

## Tests

 * Tests are implemented using `pytest`. Run them with `make test`.
 * Running on a Macmini M1 8gb takes around 5~10mins to run the HuggingFace tests. Which uses an local LLM and a local embeddings model from HuggingFace.

## License

Pedro Dias - [@pedromdias](https://twitter.com/pedromdias)

Licensed under the Apache license, version 2.0 (the "license"); You may not use this file except in compliance with the license. You may obtain a copy of the license at:

    http://www.apache.org/licenses/LICENSE-2.0.html

Unless required by applicable law or agreed to in writing, software distributed under the license is distributed on an "as is" basis, without warranties or conditions of any kind, either express or implied. See the license for the specific language governing permissions and limitations under the license.
