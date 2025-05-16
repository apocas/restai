#!/bin/bash

# Create a new environment for cudnn
ENV_NAME=".venv-cudnn8"

python3 -m venv $ENV_NAME
source $ENV_NAME/bin/activate

uv pip install nvidia-cudnn-cu11==8.6.0.163

echo "[INFO] cuDNN 8.6.0.163 installed in $ENV_NAME."
