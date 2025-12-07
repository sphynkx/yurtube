"""
TODO: rework to dotenv

Remote storage configuration.
- STORAGE_PROVIDER: "local" | "remote" (preferred selector)
- STORAGE_REMOTE_ADDRESS: gRPC server address
- STORAGE_REMOTE_TLS: enable TLS for gRPC channel
- STORAGE_REMOTE_TOKEN: bearer token passed in gRPC metadata
- STORAGE_REMOTE_BASE_PREFIX: logical prefix for paths if server expects base dir
- STORAGE_GRPC_MAX_MSG_MB: gRPC max message size in MB
"""

# Backend selector
STORAGE_PROVIDER = ""  # set to "remote" to use gRPC 

# Remote client settings
STORAGE_REMOTE_ADDRESS = "127.0.0.1:50070"
STORAGE_REMOTE_TLS = False
STORAGE_REMOTE_TOKEN = ""
STORAGE_REMOTE_BASE_PREFIX = ""
STORAGE_GRPC_MAX_MSG_MB = 64