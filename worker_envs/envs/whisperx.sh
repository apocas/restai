#!/bin/bash

ENV_NAME=".venvs/.venv-whisperx"

python3 -m venv $ENV_NAME
source $ENV_NAME/bin/activate

uv pip install nvidia-cudnn-cu11==8.6.0.163 \
  whisperx==3.3.4 \
  torch==2.6.0 \
  python-dotenv==1.1.0

echo "[INFO] $ENV_NAME installed."
