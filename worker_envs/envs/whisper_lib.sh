#!/bin/bash

ENV_NAME=".venvs/.venv-whisper_lib"

uv venv $ENV_NAME --allow-existing
source $ENV_NAME/bin/activate

uv pip install setuptools
uv pip install openai-whisper==20240930 \
  python-dotenv

echo "[INFO] $ENV_NAME installed."
