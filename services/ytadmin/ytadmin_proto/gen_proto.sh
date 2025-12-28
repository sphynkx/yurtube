#!/usr/bin/env bash
set -euo pipefail

# Generate stubs from yurtube.proto
# Make sure that yurtube.proto is identical to one from ytadmin service!!

cd "$(dirname "$0")"

source ../../../.venv/bin/activate 

python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  yurtube.proto

sed -i 's/^import yurtube_pb2 as yurtube__pb2/from . import yurtube_pb2 as yurtube__pb2/' yurtube_pb2_grpc.py

echo "Generated: yurtube_pb2.py yurtube_pb2_grpc.py in $(pwd)"
