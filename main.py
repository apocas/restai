import uvicorn

from restai.config import RESTAI_PORT
from restai.main import app

if __name__ == "__main__":
    port = int(RESTAI_PORT)

    print("Starting server on port " + str(port))
    uvicorn.run(app, host="0.0.0.0", port=port)
