import sys
sys.setrecursionlimit(20000)

# Force Pydantic to fully resolve all forward references at test collection time,
# before any TestClient instances are created. This prevents the cumulative
# __pydantic_core_schema__ AttributeError that occurs when 200+ TestClient
# instances each try to resolve schemas.
from restai.models.models import (
    TeamModel, User, ProjectModel, ProjectResponse,
    LLMModel, EmbeddingModel, ProjectBaseModel,
    WidgetResponse, WidgetCreatedResponse, WidgetConfig,
    SettingsResponse, SettingsUpdate,
)
for model in [
    TeamModel, User, ProjectModel, ProjectResponse,
    LLMModel, EmbeddingModel, ProjectBaseModel,
    WidgetResponse, WidgetCreatedResponse, WidgetConfig,
    SettingsResponse, SettingsUpdate,
]:
    model.model_rebuild()
