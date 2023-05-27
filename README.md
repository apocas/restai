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

## Endpoints:

### Project

A project is an abstract entity basically a tenant. You may have multiple projects and each project has its own embeddings, loaders and llms.

**GET /projects**

- Description: Lists all the projects.
- Request Payload: None.
- Response: A JSON object containing the list of all projects.

**GET /projects/{projectName}**

- Description: Get the specific project details.
- Request Payload: None.
- Path Parameters: 'projectName' which represents the name of the project.
- Response: A JSON object with details about the specified project including project name, embeddings, documents and metadatas. 
- Errors: 404 if project not found.

**DELETE /projects/{projectName}**

- Description: Deletes the specific project.
- Request Payload: None.
- Path Parameters: 'projectName' which represents the name of the project.
- Response: A JSON object with the name of the deleted project.
- Errors: 500 if there is an error while deleting the project.

**POST /projects**

- Description: Creates a new project.
- Request Payload: JSON representation of 'ProjectModel'.
- Response: A JSON object with the name of the created project.
- Errors: 500 if there is an error while creating the project.

### Embeddings

**POST /projects/{projectName}/ingest/url**

- Description: Ingests data into a specific project from a provided URL.
- Request Payload: JSON representation of 'IngestModel'.
- Path Parameters: 'projectName' which represents the name of the project.
- Response: A JSON object with details about the ingested data.
- Errors: 500 if there is an error while ingesting the data.

**POST /projects/{projectName}/ingest/upload**

- Description: Ingests data into a specific project from an uploaded file.
- Request Payload: File to be ingested into the system.
- Path Parameters: 'projectName' which represents the name of the project.
- Response: A JSON object with details about the ingested file including filename, type, texts, and documents.
- Errors: 500 if there is an error while ingesting the data.

### LLMs

**POST /projects/{projectName}/question**

- Description: Asks a question to a specific project.
- Request Payload: JSON representation of 'QuestionModel'.
- Path Parameters: 'projectName' which represents the name of the project.
- Response: A JSON object containing the asked question and the corresponding answer.
- Errors: 500 if there is an error while asking the question.

**POST /projects/{projectName}/chat**

- Description: Send a chat message to a specific project.
- Request Payload: JSON representation of 'ChatModel'.
- Path Parameters: 'projectName' which represents the name of the project.
- Response: A JSON object containing the sent message, the response, and an id for the chat.
- Errors: 500 if there is an error while sending the message.

## Tests

 * Tests are implemented using `pytest`. Run them with `make test`.

## License

Pedro Dias - [@pedromdias](https://twitter.com/pedromdias)

Licensed under the Apache license, version 2.0 (the "license"); You may not use this file except in compliance with the license. You may obtain a copy of the license at:

    http://www.apache.org/licenses/LICENSE-2.0.html

Unless required by applicable law or agreed to in writing, software distributed under the license is distributed on an "as is" basis, without warranties or conditions of any kind, either express or implied. See the license for the specific language governing permissions and limitations under the license.
