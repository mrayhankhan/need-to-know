"""Deploy Need-to-Know to a Hugging Face Space (Docker SDK, free CPU).

Usage:  HF_TOKEN=hf_xxx python scripts/deploy_hf.py <hf-username>/need-to-know [--llm]
The Space builds the same Dockerfile CI tests: FalkorDB and the app in one container on port 7860.
With --llm, the token is also stored as a Space secret so answers can be phrased by a model.
"""

import os
import sys
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parent.parent
FRONT = """---
title: Need-to-Know
emoji: 🗂️
colorFrom: gray
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: A company brain that knows who is allowed to know what
---

"""


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    repo = sys.argv[1]
    token = os.environ.get("HF_TOKEN")
    if not token:
        sys.exit("Set HF_TOKEN")
    api = HfApi(token=token)
    api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        readme = Path(tmp) / "README.md"
        readme.write_text(FRONT + (ROOT / "README.md").read_text(encoding="utf-8"), encoding="utf-8")
        api.upload_folder(repo_id=repo, repo_type="space", folder_path=str(ROOT),
                          ignore_patterns=[".git/*", ".github/*", "tests/*", "results/shots/*", "**/__pycache__/*", "README.md", "docs/*"],
                          commit_message="Deploy Need-to-Know")
        api.upload_file(repo_id=repo, repo_type="space", path_or_fileobj=str(readme), path_in_repo="README.md",
                        commit_message="Space README")
    if "--llm" in sys.argv:
        api.add_space_secret(repo, "HF_TOKEN", token)
    print(f"https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()
