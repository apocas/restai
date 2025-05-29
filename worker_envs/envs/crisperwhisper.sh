#!/bin/bash

ENV_NAME=".venvs/.venv-crisperwhisper"

python3 -m venv $ENV_NAME
source $ENV_NAME/bin/activate

uv pip install transformers==4.44.2 \
  torch==2.4.0 \
  accelerate==0.33.0

echo "[INFO] $ENV_NAME installed."
