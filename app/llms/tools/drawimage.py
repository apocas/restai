from langchain.tools import BaseTool


class DrawImage(BaseTool):
    name = "Draw on Image"
    description = "use this tool to draw objects on an image. Example: draw a square around.."
    return_direct = True

    def _run(self, query: str) -> str:
        return {"type": "describeimage", "image": None, "prompt": query}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")
