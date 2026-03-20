#!/bin/bash

ENV_NAME=".venvs/.venv-granite-speech"

uv venv $ENV_NAME
source $ENV_NAME/bin/activate

uv pip install "transformers>=4.52.4" \
  torch \
  torchaudio \
  peft \
  soundfile \
  accelerate

echo "[INFO] $ENV_NAME installed."
