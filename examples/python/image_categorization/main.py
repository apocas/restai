import os
import base64
from PIL import Image
from io import BytesIO
import requests
from requests import Response
from requests.auth import HTTPBasicAuth

"""
Categorize images into "sunny" or "overcast".
It uses a Vision model to describe the image and then a Classifier model to categorize the description.
"""

labels: list[str] = ["overcast", "sunny"]

basic: HTTPBasicAuth = HTTPBasicAuth('demo', 'demo')


def image_to_base64(image_path) -> str:
    with Image.open(image_path) as img_obj:
        with BytesIO() as buffer:
            img_obj.save(buffer, 'JPEG')
            return base64.b64encode(buffer.getvalue()).decode()


for img in os.listdir('images'):
    img_b64: str = image_to_base64(os.path.join('images', img))
    req: Response = requests.post('https://ai.ince.pt/projects/vision/question', auth=basic,
                                  json={"question": "Describe this image, be detailed.", "image": img_b64,
                                        "lite": True},
                                  timeout=190)
    output = req.json()["answer"]

    req = requests.post('https://ai.ince.pt/tools/classifier', auth=basic, json={"sequence": output, "labels": labels},
                        timeout=190)
    output = req.json()
    print("####################")
    print(img)
    print(output["labels"])
    print(output["scores"])
