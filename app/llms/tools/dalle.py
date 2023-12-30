import base64
from langchain.tools import BaseTool
from langchain.chains import LLMChain
from langchain.llms import OpenAI
from langchain.prompts import PromptTemplate
from langchain.utilities.dalle_image_generator import DallEAPIWrapper
import requests


class DalleImage(BaseTool):
    name = "Dall-E Image Generator"
    description = "use this tool when you need to generate an image using Dall-E."
    return_direct = True
    disableboost = False

    def _run(self, query: str) -> str:
        if self.disableboost == False:
            llm = OpenAI(temperature=0.9)
            prompt = PromptTemplate(
                input_variables=["image_desc"],
                template="Generate a detailed prompt to generate an image based on the following description: {image_desc}",
            )
            chain = LLMChain(llm=llm, prompt=prompt)
            prompt = chain.run(query)

            model = DallEAPIWrapper()
            model.model_name = "dall-e-3"

            image_url = model.run(prompt)
        else:
            image_url = model.run(query)

        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        return {"type": "dalle", "image": base64.b64encode(image_data).decode('utf-8'), "prompt": prompt}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")
