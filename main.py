import os
import uvicorn

from app.main import app


if __name__ == "__main__":
    port = 9000
    if "RESTAI_PORT" in os.environ:
        port = int(os.environ["RESTAI_PORT"])

    print("Starting server on port " + str(port))
    uvicorn.run(app, host="0.0.0.0", port=port)
