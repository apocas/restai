# restai

* RESTAI is a simple generic REST API that allows to create embeddings from multiple datatypes and then interact with them using a LLM.
* This LLM may be an OpenAI based model, llamacpp, gpt4all or any other LLM supported by langchain.
* If you want to be completely offline, you may use the `gpt4all` LLM and `huggingface` embeddings.
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

* Embeddings: `huggingface` (HuggingFace), `openai` (OpenAI)
* LLM: `gpt4all` (ggml-gpt4all-j-v1.3-groovy.bin), `llamacpp` (ggml-model-q4_0.bin), `openai` (OpenAI)
* It's very easy to add support for more [embeddings](modules/embeddings.py), [loaders](modules/loaders.py) and [LLMs](modules/llms.py).

## Example usage

**POST /projects ({"name": "test_openai",  "embeddings": "openai", "llm": "openai"})**
```json 
{"project": "test_openai"}
```

**POST /projects/test_openai/ingest/upload (upload a [test.txt](tests/test.txt))**
```json 
{"project": "test_openai", "embeddings": "openai", "documents": 2, "metadatas": 2}
```

**POST /projects/test_openai/question ({"question": "What is the secret?"})**
```json 
{"question": "What is the secret?", "answer": "The secret is that ingenuity should be bigger than politics and corporate greed."}
```

**POST /projects/test_openai/question ({"system": "You are a digital assistant, answer only in french.", "question": "What is the secret?"})**
```json 
{"question": "What is the secret?", "answer": "Le secret est que l'ingéniosité doit être plus grande que la politique et la cupidité des entreprises."}
```

## Endpoints:

### Project

---

A project is an abstract entity basically a tenant. You may have multiple projects and each project has its own embeddings, loaders and llms.

**GET /projects**

- Description: Lists all the projects.
- Response:
    ```json
    {
      "projects": [
        "test_openai",
        "test_openai2"
      ]
    }
    ```

**GET /projects/{projectName}**

- Description: Get the specific project details.
- Response:
    ```json
    {
      "project": "test_openai",
      "embeddings": "openai",
      "documents": 2,
      "metadatas": 2,
    }
    ```
- Errors: 404 if project not found.

**DELETE /projects/{projectName}**

- Description: Deletes the specific project.
- Request Payload: None.
- Response: A JSON object with the name of the deleted project.
- Errors: 500 if there is an error while deleting the project.

**POST /projects**

- Description: Creates a new project.
- Request Payload:
    ```json
    {
      "name": "string",
      "embeddings": "string (Optional)",
      "embeddings_model": "string (Optional)",
      "llm": "string (Optional)"
    }
    ```
- Response: A JSON object with the name of the created project.
- Errors: 500 if there is an error while creating the project.

### Embeddings

---

**POST /projects/{projectName}/ingest/url**

- Description: Ingests data into a specific project from a provided URL.
- Request Payload:
    ```
    {
      "url": "https://www.example.com",
    }
    ```
- Response:
    ```json
    {
      "project": "test_openai",
      "embeddings": "openai",
      "documents": 2,
      "metadatas": 2
    }
    ```
- Errors: 500 if there is an error while ingesting the data.

**POST /projects/{projectName}/ingest/upload**

- Description: Ingests data into a specific project's embeddings from an uploaded file.
- Request Payload: File to be ingested into the system.
- Response:
    ```json
    {
      "project": "test_openai",
      "embeddings": "openai",
      "documents": 2,
      "metadatas": 2
    }
    ```
- Errors: 500 if there is an error while ingesting the data.

### LLMs

---

**POST /projects/{projectName}/question**

- Description: Asks a question to a specific project.
- Request Payload:
    ```json
    {
      "question": "string",
      "llm": "string (Optional)",
      "system": "string (Optional - System message for LLMs that support it)"
    }
    ```
- Response:
    ```json
    {
      "question": "What is the secret?",
      "answer": "The secret is that ingenuity should be bigger than politics and corporate greed."}
    ```
- Errors: 500 if there is an error while asking the question.

**POST /projects/{projectName}/chat**

- Description: Send a chat message to a specific project.
- Request Payload:
    ```json
    {
      "message": "string",
      "id": "string (Optional - if not provided, a new chat will be created)",
    }
    ```
- Response:
    ```json
    {
      "id": "string",
      "message": "string",
      "response": "string"
    }
    ```
- Errors: 500 if there is an error while sending the message.

## [Swagger](https://apocas.github.io/restai/)

## Tests

 * Tests are implemented using `pytest`. Run them with `make test`.
 * Running on a Macmini M1 8gb takes around 5~10mins to run the HuggingFace tests. Which uses an local LLM and a local embeddings model from HuggingFace.

## License

Pedro Dias - [@pedromdias](https://twitter.com/pedromdias)

Licensed under the Apache license, version 2.0 (the "license"); You may not use this file except in compliance with the license. You may obtain a copy of the license at:

    http://www.apache.org/licenses/LICENSE-2.0.html

Unless required by applicable law or agreed to in writing, software distributed under the license is distributed on an "as is" basis, without warranties or conditions of any kind, either express or implied. See the license for the specific language governing permissions and limitations under the license.
