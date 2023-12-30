from langchain.tools import BaseTool


class DescribeImage(BaseTool):
    name = "Describe Image"
    description = "use this tool to describe an image."
    return_direct = True

    def _run(self, query: str) -> str:
        return {"type": "describeimage", "image": None, "prompt": query}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")
