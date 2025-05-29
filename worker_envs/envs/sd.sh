#!/bin/bash

ENV_NAME=".venvs/.venv-sd"

python3 -m venv $ENV_NAME
source $ENV_NAME/bin/activate

uv pip install transformers==4.46.3 \
  xformers==0.0.28.post3 \
  optimum==1.13.1 \
  accelerate==1.2.1 \
  bitsandbytes==0.44.1 \
  diffusers==0.31.0 \
  torch==2.5.1 \
  torchvision==0.20.1 \
  kornia==0.7.4 \
  timm==1.0.12

echo "[INFO] $ENV_NAME installed."
