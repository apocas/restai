import base64
from restai.models.models import ImageModel

import os
import google.generativeai as genai

genai.configure(api_key=os.environ['GOOGLE_API_KEY'])

def generate(imageModel: ImageModel):
    imagen = genai.ImageGenerationModel("imagen-3.0-generate-001")
    result = imagen.generate_images(
        prompt=imageModel.prompt,
        number_of_images=1,
        safety_filter_level="block_only_high",
        person_generation="allow_adult",
        aspect_ratio="3:4",
    )
    
    return base64.b64encode(result.images[0]._pil_image).decode('utf-8')
