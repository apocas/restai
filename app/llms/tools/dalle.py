import base64
from langchain.tools import BaseTool
from langchain.chains import LLMChain
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_community.utilities.dalle_image_generator import DallEAPIWrapper
import requests
from typing import Optional
from langchain.callbacks.manager import (
    CallbackManagerForToolRun,
)


class DalleImage(BaseTool):
    name = "Dall-E Image Generator"
    description = "use this tool when you need to generate an image using Dall-E."
    return_direct = True

    def _run(self, query: str, run_manager: Optional[CallbackManagerForToolRun] = None) -> str:
        
        if run_manager.tags[0].boost == True:
            llm = ChatOpenAI(temperature=0.9, model_name="gpt-3.5-turbo")
            prompt = PromptTemplate(
                input_variables=["image_desc"],
                template="Generate a detailed prompt to generate an image based on the following description: {image_desc}",
            )
            chain = LLMChain(llm=llm, prompt=prompt)
            prompt = chain.run(query)
        else:
            prompt = run_manager.tags[0].question

        model = DallEAPIWrapper()
        model.model_name = "dall-e-3"
        image_url = model.run(prompt)

        response = requests.get(image_url)
        response.raise_for_status()
        image_data = response.content
        return {"type": "dalle", "image": base64.b64encode(image_data).decode('utf-8'), "prompt": prompt}

    async def _arun(self, query: str) -> str:
        raise NotImplementedError("N/A")
