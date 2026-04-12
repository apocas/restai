import sys
sys.setrecursionlimit(20000)

# Force ALL Pydantic models to fully resolve their schemas in the main thread
# under the raised recursion limit. Without this, TestClient triggers schema
# resolution inside a thread pool where the recursion limit may not be sufficient.
import inspect
from restai.models import models as _models_module
from pydantic import BaseModel

for _name, _obj in inspect.getmembers(_models_module):
    if inspect.isclass(_obj) and issubclass(_obj, BaseModel) and _obj is not BaseModel:
        try:
            _obj.model_rebuild()
        except Exception:
            pass
