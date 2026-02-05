#!/usr/bin/env bash
set -euo pipefail

# Generate stubs from ytcms.proto
# Make sure that ytcms.proto is identical to one from ytcms service!!

cd "$(dirname "$0")"

source ../../../.venv/bin/activate 

python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  ytcms.proto

sed -i 's/^import ytcms_pb2 as ytcms__pb2/from . import ytcms_pb2 as ytcms__pb2/' ytcms_pb2_grpc.py

echo "Generated: ytcms_pb2.py ytcms_pb2_grpc.py in $(pwd)"
