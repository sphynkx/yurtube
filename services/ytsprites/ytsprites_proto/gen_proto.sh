#!/usr/bin/env bash
set -euo pipefail

# Generate stubs from ytsprites.proto
# Make sure that ytsprites.proto is identical to one from ytsprites service!!

cd "$(dirname "$0")"

source ../../../.venv/bin/activate 

python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  ytsprites.proto

echo "Generated: ytsprites_pb2.py ytsprites_pb2_grpc.py in $(pwd)"
