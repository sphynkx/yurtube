#!/usr/bin/env bash
set -euo pipefail

# Generate stubs from captions.proto
# Make sure that captions.proto is identical to one from ytcms service!!

cd "$(dirname "$0")"

source ../../../.venv/bin/activate 

python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  captions.proto

echo "Generated: captions_pb2.py captions_pb2_grpc.py in $(pwd)"
