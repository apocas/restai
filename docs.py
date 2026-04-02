from fastapi.openapi.utils import get_openapi
from restai.main import app
from restai.routers import llms, embeddings, projects, tools, users, proxy, statistics, auth, teams, settings, direct, evals
import json

# Register routers that are normally added in lifespan
app.include_router(llms.router, tags=["LLMs"])
app.include_router(embeddings.router, tags=["Embeddings"])
app.include_router(projects.router)
app.include_router(tools.router, tags=["Tools"])
app.include_router(users.router, tags=["Users"])
app.include_router(proxy.router, tags=["Proxy"])
app.include_router(statistics.router, tags=["Statistics"])
app.include_router(auth.router, tags=["Auth"])
app.include_router(teams.router, tags=["Teams"])
app.include_router(settings.router, tags=["Settings"])
app.include_router(direct.router, tags=["Direct Access"])
app.include_router(evals.router)

schema = get_openapi(
    title=app.title,
    version=app.version,
    openapi_version=app.openapi_version,
    description=app.description,
    routes=app.routes,
)

with open('./docs/swagger/openapi.json', 'w') as f:
    json.dump(schema, f, indent=2)

print(f"OpenAPI schema written: {len(schema.get('paths', {}))} endpoints")
