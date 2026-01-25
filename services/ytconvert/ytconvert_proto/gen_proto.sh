#!/usr/bin/env bash
set -euo pipefail

# Generate stubs from ytconvert.proto
# Make sure that ytconvert.proto is identical to one from ytconvert service!!

cd "$(dirname "$0")"

source ../../../.venv/bin/activate 

python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  ytconvert.proto

sed -i 's/^import ytconvert_pb2 as ytconvert__pb2/from . import ytconvert_pb2 as ytconvert__pb2/' ytconvert_pb2_grpc.py

echo "Generated: ytconvert_pb2.py ytconvert_pb2_grpc.py in $(pwd)"
