#!/bin/bash

ENV_NAME=".venvs/.venv-flux2"

uv venv $ENV_NAME --allow-existing
source $ENV_NAME/bin/activate

uv pip install transformers \
  accelerate \
  bitsandbytes \
  torch \
  torchvision \
  python-dotenv \
  "diffusers @ git+https://github.com/huggingface/diffusers.git"

echo "[INFO] $ENV_NAME installed."
