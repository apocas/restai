import typer
import uvicorn

from restai.config import RESTAI_PORT
from restai.main import app as restai_app

app = typer.Typer()

@app.command()
def serve(
    host: str = "0.0.0.0",
    port: int = 8080,
):

    portf = int(port or RESTAI_PORT)

    print("Starting RESTai server on port " + str(portf))

    uvicorn.run(restai_app.main.app, host=host, port=portf, forwarded_allow_ips="*")

