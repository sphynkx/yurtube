#!/usr/bin/env bash
set -euo pipefail

# Generate stubs from yttrans.proto
# Make sure that yttrans.proto is identical to one from yurtube service!!

cd "$(dirname "$0")"

source ../../../.venv/bin/activate 

python -m grpc_tools.protoc \
  -I . \
  --python_out=. \
  --grpc_python_out=. \
  yttrans.proto

sed -i 's/^import yttrans_pb2 as yttrans__pb2/from . import yttrans_pb2 as yttrans__pb2/' yttrans_pb2_grpc.py

echo "Generated: yttrans_pb2.py yttrans_pb2_grpc.py in $(pwd)"
