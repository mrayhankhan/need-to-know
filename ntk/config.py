import os

FALKORDB_HOST = os.getenv("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(os.getenv("FALKORDB_PORT", "6379"))
FALKORDB_USERNAME = os.getenv("FALKORDB_USERNAME") or None
FALKORDB_PASSWORD = os.getenv("FALKORDB_PASSWORD") or None

# Optional: Hugging Face Inference Providers (OpenAI-compatible router).
# Without a token every answer is still produced, using deterministic templates.
HF_TOKEN = os.getenv("HF_TOKEN") or None
HF_MODEL = os.getenv("HF_MODEL", "meta-llama/Llama-3.1-8B-Instruct")
HF_BASE_URL = os.getenv("HF_BASE_URL", "https://router.huggingface.co/v1")

# One graph per company. FalkorDB keeps them fully isolated in one instance.
TENANTS = {"northwind": "Northwind Labs", "bluefin": "Bluefin Health"}

# Deepest group nesting we follow when resolving access.
MAX_HOPS = 8
