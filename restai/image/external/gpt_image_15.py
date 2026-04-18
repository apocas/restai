"""OpenAI gpt-image-1.5 image generator.

Uses the OpenAI Python SDK directly (not the LangChain DallEAPIWrapper, which
hard-codes dall-e-*). The API key comes from platform settings; see
`restai/image/external/_openai.py`.
"""
import base64

import requests
from openai import OpenAI

from restai.image.external._openai import get_openai_api_key
from restai.models.models import ImageModel


def generate(imageModel: ImageModel):
    api_key = get_openai_api_key()
    client = OpenAI(api_key=api_key)

    # OpenAI's /v1/images/generations accepts `response_format="b64_json"` for
    # most image models; gpt-image-* returns base64 data by default so a URL
    # fallback keeps us robust against either shape.
    result = client.images.generate(
        model="gpt-image-1.5",
        prompt=imageModel.prompt,
        n=1,
    )
    data = result.data[0]
    if getattr(data, "b64_json", None):
        return data.b64_json
    if getattr(data, "url", None):
        response = requests.get(data.url)
        response.raise_for_status()
        return base64.b64encode(response.content).decode("utf-8")
    raise RuntimeError("gpt-image-1.5 returned neither b64_json nor url")
