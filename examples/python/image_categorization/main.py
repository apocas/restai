import os
import base64
from PIL import Image
from io import BytesIO
import requests
from requests.auth import HTTPBasicAuth

"""
Categorize images into "sunny" or "overcast".
It uses a Vision model to describe the image and then a Classifier model to categorize the description.
"""

labels = ["overcast", "sunny"]

basic = HTTPBasicAuth('demo', 'demo')

def image_to_base64(image_path):
    with Image.open(image_path) as img:
        with BytesIO() as buffer:
            img.save(buffer, 'JPEG')
            return base64.b64encode(buffer.getvalue()).decode()

for img in os.listdir('images'):
    imgb64 = image_to_base64(os.path.join('images', img))
    req = requests.post('https://ai.ince.pt/projects/vision/question', auth=basic, json={"question": "Describe this image, be detailed.", "image": imgb64, "lite": True}, timeout=190)
    output = req.json()["answer"]
    
    req = requests.post('https://ai.ince.pt/tools/classifier', auth=basic, json={"sequence": output, "labels": labels}, timeout=190)
    output = req.json()
    print("####################")
    print(img)
    print(output["labels"])
    print(output["scores"])