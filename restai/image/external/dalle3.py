import base64

import requests
from langchain_community.utilities.dalle_image_generator import DallEAPIWrapper

from restai.image.external._openai import get_openai_api_key
from restai.models.models import ImageModel


def generate(imageModel: ImageModel):
    api_key = get_openai_api_key()
    model = DallEAPIWrapper(openai_api_key=api_key)
    model.model_name = "dall-e-3"
    image_url = model.run(imageModel.prompt)

    response = requests.get(image_url)
    response.raise_for_status()
    image_data = response.content
    return base64.b64encode(image_data).decode("utf-8")
