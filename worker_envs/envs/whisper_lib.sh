#!/bin/bash

ENV_NAME=".venvs/.venv-whisper_lib"

python3 -m venv $ENV_NAME
source $ENV_NAME/bin/activate

uv pip install openai-whisper==20240930

echo "[INFO] $ENV_NAME installed."
