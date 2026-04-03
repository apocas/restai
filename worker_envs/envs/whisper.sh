#!/bin/bash

ENV_NAME=".venvs/.venv-whisper"

uv venv $ENV_NAME --allow-existing
source $ENV_NAME/bin/activate

uv pip install "transformers" \
  torch \
  torchaudio \
  peft \
  soundfile \
  accelerate \
  python-dotenv

echo "[INFO] $ENV_NAME installed."
