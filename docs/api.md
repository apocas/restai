<!-- markdownlint-disable MD024 -->
# API Endpoints

- [API Endpoints](#api-endpoints)
  - [Create a new Project](#create-a-new-project)
  - [Get Project list](#get-project-list)
  - [Get a Project](#get-a-project)
  - [Create an user](#create-an-user)
  - [Get an user](#get-an-user)
  - [Generate an user's API key](#generate-an-users-api-key)
  - [Get user list](#get-user-list)
  - [Get an LLM](#get-an-llm)
  - [Get all LLMs](#get-all-llms)
  - [Generate a completion](#generate-a-completion)
  - [Generate an image](#generate-an-image)
  - [Get image generators list](#get-image-generators-list)

## Create a new Project

```shell
POST /projects
```

### Parameters

- `name`: (required) project name
- `embeddings`: (optional) embeddings name to be used in the project [RAG]
- `llm`: LLM name to be used in the project
- `type`: project type (rag, vision, router, inference)
- `vectorstore`: Vector name to be used [RAG]
  
### Response

- `project`: project name

## Get Project list

```shell
GET /projects
```

### Response

- `projects`: array with all projects, follow the same structure as [Get a Project](#get-a-project)

## Get a Project

```shell
GET /projects/{projectname}
```

### Parameters

- `projectname`: (required) Project name

### Response

- `name`: Project name, normalized used to identify the project.
- `human_name`: Human project name, unnormalized, human friendly.
- `human_description`: Project description, human friendly.
- `type`: Project type
- `llm`: LLM to be used by the project
- `chunks`: How many chunks were ingested [RAG]
- `embeddings`: embeddings model to be used [RAG]
- `k`: K value [RAG]
- `score`: Score cutoff [RAG]
- `vectorstore`: Vectorstore name [RAG]
- `system`: System message
- `censorship`: Censhorship message to be sent when Retrival process fails [RAG]
- `llm_rerank`: LLM rerank [RAG]
- `colbert_rerank`: Colbert rerank [RAG]
- `tools`: tools to be used in the question [AGENT]
- `tables`: tables to be used in the question [RAGSQL]
- `connection`: connection string to the database [RAGSQL]
- `entrances`: array with routes [ROUTER]
- `llm_type`: LLM type
- `llm_privacy`: LLM privacy

## Create an user

```shell
POST /users
```

### Parameters

- `username`: (required) username for the new user
- `password`: (required) password for the new user
- `is_admin`: (optional) boolean to specify if the user is an admin
- `is_private`: (optional) boolean to specify if the user is locked to local/private LLMs only

### Response

- `username`: user question
- `is_admin`: answer
- `is_private`: array with sources used to generate the answer

## Get an user

```shell
GET /users/{username}
```

### Parameters

- `username`: (required) username

### Response

- `username`: user question
- `is_admin`: answer
- `is_private`: array with sources used to generate the answer
- `projects`: array with projects the user has access to

## Generate an user's API key

```shell
POST /users/{username}/apikey
```

### Parameters

- `username`: (required) username

### Response

- `api_key`: user's API key, keep it safe if lost new one will need to be generated

## Get user list

```shell
GET /users
```

### Response

- `users`: array with all users, follow the same structure as [Get an user](#get-an-user)

## Get an LLM

```shell
GET /llms/{llmname}
```

### Parameters

- `llmname`: (required) LLM name

### Response

- `name`: LLM Name
- `class_name`: Class name
- `options`: String containing the options used to initialize the LLM
- `privacy`: public or private (local)
- `description`: Description
- `type`: qa, chat, vision

## Get all LLMs

```shell
GET /llms
```

### Response

- `llms`: array with all LLMs, follow the same structure as [Get an LLM](#get-an-llm)

## Generate a completion

```shell
POST /projects/{projectName}/question
```

### Parameters

- `projectName`: (required) project name
- `question`: (required) user message
- `system`: (optional) system message, if not provided project's system message will be used
- `stream`: (optional) boolean to specify if this completion is streamed
  
Advanced parameters (optional):

- `score`: (optional) cutoff score, if not provided project's cutoff score will be used [RAG]
- `k`: (optional) k value, if not provided project's k value will be used [RAG]
- `colbert_rerank`: (optional) boolean to specify if colbert reranking is enabled [RAG]
- `llm_rerank`: (optional) boolean to specify if llm reranking is enabled [RAG]
- `eval`: (optional) rag evaluation [RAG]
- `tables`: (optional) tables to be used in the question [RAGSQL]
- `negative`: (optional) negative prompt [VISION]
- `image`: (optional) image [VISION]

### Response

- `question`: user question
- `answer`: answer
- `sources`: array with sources used to generate the answer
- `type`: type (inference, rag, vision, ragsql, etc)
- `tokens.input`: number of tokens used in the question
- `tokens.output`: number of tokens used in the answer
- `image`: image [VISION] [ROUTER]
- `evaluation.reason`: if eval was provided, the reason for the score [RAG]
- `evaluation.score`: if eval was provided, the score [RAG]

## Generate an image

```shell
POST /image/{generator}/generate
```

### Parameters

- `prompt`: (required) project name

### Response

- `image`: image [VISION] [ROUTER]

## Get image generators list

```shell
GET /image
```

### Parameters

### Response

- `generators`: array with all image generators names
