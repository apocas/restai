import logging
import traceback

from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException, Request
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from restai import config
from restai.auth import get_current_username
from restai.models.models import ClassifierModel, ClassifierResponse, OllamaInstanceModel, OllamaModelInfo, OllamaModelPullRequest, OllamaModelPullResponse, Tool, User

logging.basicConfig(level=config.LOG_LEVEL)
logging.getLogger("passlib").setLevel(logging.ERROR)

router = APIRouter()


@router.post("/tools/classifier", response_model=ClassifierResponse)
async def classifier(
    request: Request,
    input_model: ClassifierModel,
    _: User = Depends(get_current_username),
):
    try:
        return request.app.state.brain.classify(input_model)
    except Exception as e:
        logging.error(e)
        traceback.print_tb(e.__traceback__)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tools/agent", response_model=list[Tool])
async def get_tools(request: Request, _: User = Depends(get_current_username)):

    _tools = []

    for tool in request.app.state.brain.get_tools():
        _tools.append(
            Tool(name=tool.metadata.name, description=tool.metadata.description)
        )

    return _tools


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
            
            models_info.append(
                OllamaModelInfo(
                    name=model.get("name", "") or model.get("model", ""),
                    size=model.get("size", 0),
                    digest=model.get("digest", ""),
                    modified_at=modified_at,
                    details=details
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
