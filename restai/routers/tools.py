import logging
import os
import traceback

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from restai import config
from restai.auth import get_current_username, get_current_username_admin
from restai.database import DBWrapper, get_db_wrapper
from restai.models.models import ClassifierModel, ClassifierResponse, MCPProbeRequest, OllamaInstanceModel, OllamaModelInfo, OllamaModelPullRequest, OllamaModelPullResponse, Tool, User

logging.basicConfig(level=config.LOG_LEVEL)

router = APIRouter()


@router.get("/tools/classifiers")
async def list_classifiers(
    _: User = Depends(get_current_username),
):
    """List available zero-shot classifier models."""
    from restai.brain import Brain
    return {
        "classifiers": [
            {"id": k, "name": v} for k, v in Brain.VALID_CLASSIFIERS.items()
        ],
        "default": Brain.DEFAULT_CLASSIFIER,
    }


@router.post("/tools/classifier", response_model=ClassifierResponse)
async def classifier(
    request: Request,
    input_model: ClassifierModel,
    _: User = Depends(get_current_username),
):
    """Classify text into provided labels using zero-shot classification."""
    try:
        return request.app.state.brain.classify(input_model)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logging.exception(e)
        raise HTTPException(status_code=500, detail="Classification failed")


@router.get("/tools/agent", response_model=list[Tool])
async def get_tools(request: Request, _: User = Depends(get_current_username)):
    """List all registered agent tools."""
    _tools = []

    for tool in request.app.state.brain.get_tools():
        _tools.append(
            Tool(name=tool.metadata.name, description=tool.metadata.description)
        )

    return _tools


def _validate_mcp_host(host: str, args: list = None):
    """Validate MCP server host — must be an HTTP(S) URL or a known safe command."""
    from restai.agent2.mcp_client import ALLOWED_MCP_STDIO_COMMANDS

    if not host or not host.strip():
        raise HTTPException(status_code=400, detail="MCP server host is required")
    host = host.strip()
    if host.startswith(("http://", "https://")):
        return  # URLs are fine
    # Stdio mode: only allow known package runners / interpreters
    cmd = os.path.basename(host)
    if cmd not in ALLOWED_MCP_STDIO_COMMANDS:
        raise HTTPException(
            status_code=400,
            detail=f"MCP stdio command '{cmd}' is not allowed. Permitted commands: {', '.join(sorted(ALLOWED_MCP_STDIO_COMMANDS))}",
        )
    # Reject shell metacharacters in args
    if args:
        import re
        for arg in args:
            if re.search(r'[;&|`$(){}]', str(arg)):
                raise HTTPException(
                    status_code=400,
                    detail=f"MCP argument contains disallowed shell characters: {arg}",
                )


@router.post("/tools/mcp/probe")
async def probe_mcp_server(
    probe_request: MCPProbeRequest,
    _: User = Depends(get_current_username),
):
    """Probe an MCP server or gateway to discover available tools/services."""
    _validate_mcp_host(probe_request.host, probe_request.args)
    try:
        # Detect MCP gateway (returns a services list instead of being a direct MCP server)
        if probe_request.host.startswith("http"):
            import httpx
            try:
                async with httpx.AsyncClient() as http_client:
                    resp = await http_client.get(
                        probe_request.host,
                        headers=probe_request.headers or {},
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if "services" in data and isinstance(data["services"], list):
                            return {
                                "type": "gateway",
                                "name": data.get("name", ""),
                                "description": data.get("description", ""),
                                "services": data["services"],
                            }
            except Exception:
                pass  # Not a gateway, fall through to MCP probe

        from llama_index.tools.mcp import BasicMCPClient, McpToolSpec

        mcp_client = BasicMCPClient(
            probe_request.host,
            args=probe_request.args or [],
            env=probe_request.env or {},
            headers=probe_request.headers or None,
        )
        mcp_tool_spec = McpToolSpec(client=mcp_client)
        tools = await mcp_tool_spec.to_tool_list_async()

        tools_info = []
        for tool in tools:
            tools_info.append({
                "name": tool.metadata.name,
                "description": tool.metadata.description,
                "schema": tool.metadata.fn_schema_str,
            })

        return {"type": "server", "tools": tools_info}
    except BaseException as e:
        msg = str(e)
        if "401" in msg or "Unauthorized" in msg:
            msg = "Authentication required. The MCP server returned 401 Unauthorized."
        logging.error(e)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to connect to MCP server at {probe_request.host}: {msg}"
        )


@router.post("/tools/ollama/models", response_model=List[OllamaModelInfo])
async def get_ollama_models(
    ollama_instance: OllamaInstanceModel,
    _: User = Depends(get_current_username),
):
    """
    Connect to an Ollama instance and retrieve all available models.
    
    Args:
        ollama_instance: OllamaInstanceModel with host and port
        
    Returns:
        List of models information from the Ollama instance
    """
    try:
        from ollama import Client
        
        # Configure Ollama client to use the specified host/port
        ollama_host = f"http://{ollama_instance.host}:{ollama_instance.port}"
        
        client = Client(
          host=ollama_host,
        )
                
        # List all models
        models_response = client.list()
        
        # Convert to our model format
        models_info = []
        for model in models_response.get("models", []):
            # Convert ModelDetails to a dictionary if it's not already
            details = model.get("details", {})
            if details and not isinstance(details, dict):
                try:
                    # Convert to dictionary using model_dump() if available (for Pydantic models)
                    if hasattr(details, "model_dump"):
                        details = details.model_dump()
                    # Or use __dict__ as fallback
                    elif hasattr(details, "__dict__"):
                        details = {k: v for k, v in details.__dict__.items() if not k.startswith("_")}
                    else:
                        # Last resort: convert to string and log warning
                        logging.warning(f"Could not convert details to dictionary: {details}")
                        details = {"raw_info": str(details)}
                except Exception as conversion_error:
                    logging.error(f"Error converting model details to dictionary: {conversion_error}")
                    details = {}
            
            # Convert datetime to string if needed
            modified_at = model.get("modified_at", "")
            if modified_at and not isinstance(modified_at, str):
                try:
                    # Convert datetime to ISO format string
                    modified_at = modified_at.isoformat() if hasattr(modified_at, "isoformat") else str(modified_at)
                except Exception as dt_error:
                    logging.error(f"Error converting modified_at to string: {dt_error}")
                    modified_at = ""
            
            model_name = model.get("name", "") or model.get("model", "")

            # Fetch capabilities and embedding_length via show()
            capabilities = None
            embedding_length = None
            try:
                show_response = client.show(model_name)
                if hasattr(show_response, "capabilities"):
                    capabilities = show_response.capabilities
                elif isinstance(show_response, dict):
                    capabilities = show_response.get("capabilities")

                model_info_data = None
                if hasattr(show_response, "model_info"):
                    model_info_data = show_response.model_info
                elif isinstance(show_response, dict):
                    model_info_data = show_response.get("model_info", {})

                if model_info_data and isinstance(model_info_data, dict):
                    for key, value in model_info_data.items():
                        if key.endswith(".embedding_length"):
                            embedding_length = value
                            break
            except Exception as show_error:
                logging.warning(f"Could not fetch show info for {model_name}: {show_error}")

            models_info.append(
                OllamaModelInfo(
                    name=model_name,
                    size=model.get("size", 0),
                    digest=model.get("digest", ""),
                    modified_at=modified_at,
                    details=details,
                    capabilities=capabilities,
                    embedding_length=embedding_length
                )
            )
        
        return models_info
    except ImportError:
        raise HTTPException(
            status_code=500, 
            detail="Ollama Python package is not installed. Please install it using 'pip install ollama'."
        )
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to connect to Ollama instance at {ollama_instance.host}:{ollama_instance.port}: {str(e)}"
        )


@router.post("/tools/ollama/pull", response_model=OllamaModelPullResponse)
async def pull_ollama_model(
    model_request: OllamaModelPullRequest,
    _: User = Depends(get_current_username),
):
    """
    Pull (download/install) a model to an Ollama instance.
    
    Args:
        model_request: Contains the model name to pull and the Ollama instance details
        
    Returns:
        Status of the pull operation
    """
    try:
        from ollama import Client
        
        # Configure Ollama client to use the specified host/port
        ollama_host = f"http://{model_request.host}:{model_request.port}"
        
        client = Client(
          host=ollama_host,
        )
        
        # Pull the requested model
        pull_response = client.pull(model_request.name)
        
        # Return the response
        return OllamaModelPullResponse(
            status="success",
            model=model_request.name,
            digest=pull_response.get("digest", None)
        )
    except ImportError:
        raise HTTPException(
            status_code=500, 
            detail="Ollama Python package is not installed. Please install it using 'pip install ollama'."
        )
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to pull model '{model_request.name}' to Ollama instance at {model_request.host}:{model_request.port}: {str(e)}"
        )


@router.get("/tools/openai-compat/models/{llm_id}")
async def list_openai_compatible_models(
    request: Request,
    llm_id: int,
    _: User = Depends(get_current_username_admin),
    db_wrapper: DBWrapper = Depends(get_db_wrapper),
):
    """List models from an OpenAI-compatible endpoint using a saved LLM's credentials (admin only)."""
    import httpx
    import json as _json

    llm_db = db_wrapper.get_llm_by_id(llm_id)
    if llm_db is None:
        raise HTTPException(status_code=404, detail="LLM not found")

    raw_options = llm_db.options or "{}"
    opts = _json.loads(raw_options) if isinstance(raw_options, str) else raw_options

    base_url = (opts.get("api_base") or opts.get("base_url") or "").rstrip("/")
    api_key = opts.get("api_key") or ""

    if not base_url:
        raise HTTPException(status_code=400, detail="This LLM has no api_base / base_url configured")

    models_url = base_url.rstrip("/")
    if not models_url.endswith("/models"):
        if not models_url.endswith("/v1"):
            models_url += "/v1"
        models_url += "/models"

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(models_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        models = []
        for m in data.get("data", []):
            models.append({
                "id": m.get("id", ""),
                "owned_by": m.get("owned_by", ""),
            })
        models.sort(key=lambda x: x["id"])
        return {"models": models}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Provider returned {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to list models: {e}")
