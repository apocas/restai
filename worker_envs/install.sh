#!/bin/bash
# This script executes all executable .sh scripts in the envs directory and its subdirectories

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVS_DIR="$SCRIPT_DIR/envs"

if [ ! -d "$ENVS_DIR" ]; then
  echo "envs directory not found at $ENVS_DIR"
  exit 1
fi

echo "Installing all environments in $ENVS_DIR"

find "$ENVS_DIR" -type f -name "*.sh" | while read -r script; do
  echo "Installing $script"
  bash "$script"
done
