#!/bin/bash
# Shared worker venv for the Z-Image / ERNIE-Image family of generators:
# - zimage_turbo      (Tongyi-MAI/Z-Image-Turbo,  ZImagePipeline)
# - z_anime           (SeeSee21/Z-Anime,          ZImagePipeline)
# - ernie_image       (baidu/ERNIE-Image,         ErnieImagePipeline)
# - ernie_image_turbo (baidu/ERNIE-Image-Turbo,   ErnieImagePipeline)
#
# We pull diffusers from main because the Z-Image and ERNIE pipeline
# classes only landed in late-2025 releases — the 0.31 pinned in the
# shared `.venv-sd` predates them.
#
# Build: `bash worker_envs/envs/zimage.sh` (the worker_envs/setup.sh
# entry point runs this for you when you bootstrap GPU envs).

ENV_NAME=".venvs/.venv-zimage"

uv venv $ENV_NAME --allow-existing
source $ENV_NAME/bin/activate

uv pip install transformers \
  accelerate \
  torch \
  torchvision \
  sentencepiece \
  protobuf \
  python-dotenv \
  gguf \
  huggingface_hub \
  "diffusers @ git+https://github.com/huggingface/diffusers.git"

echo "[INFO] $ENV_NAME installed."
