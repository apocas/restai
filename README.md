<h1 align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/restai-logo.png"/>
  </br>RestAI
</h1>

<p align="center">
  <strong>An AI framework built using LLamaindex, Langchain and Transformers.</strong>
</p>

<p align="center">
  AIaaS (AI as a Service) for everyone. Create projects and consume them using a simple REST API.
</p>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/out.gif"/>
</div>

## Features
- **Projects**: There are multiple types of projects, each with its own features. (rag, inference, vision)
- **Users**: A user represents a user of the system. It's used for authentication and authorization (basic auth). Each user may have access to multiple projects.
- **LLMs**: You may use any LLM supported by langchain and/or transformers pipes.
- **Prompts**: You may declare PROMPTs templates and then use these prompts in the LLMs.
- **Swagger**: All endpoints are documented using Swagger.
- **Frontend**: There is a frontend available

## Project Types

### RAG

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/rag.png" width="750"  style="margin: 10px;"/>
</div>

- **Embeddings**: You may use any embeddings supported by llamaindex.
- **Sandboxed mode**: RAG Projects have "sandboxed" mode, which means that a locked default answer will be given when there aren't embeddings for the provided question. This is useful for chatbots, where you want to provide a default answer when the LLM doesn't know how to answer the question, reduncing hallucination.

### Inference

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/inference.png" width="750"  style="margin: 10px;"/>
</div>

### Vision

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/llava.png" width="750"  style="margin: 10px;"/>
</div>

<div align="center">
  <img src="https://github.com/apocas/restai/blob/master/readme/assets/vision_sd.png" width="750"  style="margin: 10px;"/>
</div>
