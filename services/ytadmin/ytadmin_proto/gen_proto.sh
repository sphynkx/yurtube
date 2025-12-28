#!/usr/bin/env bash
set -euo pipefail

# Generate stubs from ytadmin.proto
# Make sure that ytadmin is identical to one from ytadmin service!!

cd "$(dirname "$0")"

source ../../../.venv/bin/activate 

python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  ytadmin.proto

sed -i 's/^import ytadmin_pb2 as ytadmin__pb2/from . import ytadmin_pb2 as ytadmin__pb2/' ytadmin_pb2_grpc.py

echo "Generated: ytadmin_pb2.py ytadmin_pb2_grpc.py in $(pwd)"
