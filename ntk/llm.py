"""Optional language model, via Hugging Face Inference Providers.

The model only ever receives text the asker is already allowed to read. It can phrase an
answer; it cannot decide access and it cannot leak what it never saw. Without HF_TOKEN
the callers fall back to deterministic templates, so the product works with no key.
"""

from __future__ import annotations

import httpx

from . import config


def available() -> bool:
    return bool(config.HF_TOKEN)


def complete(system: str, user: str, max_tokens: int = 220) -> str | None:
    if not config.HF_TOKEN:
        return None
    try:
        r = httpx.post(
            f"{config.HF_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.HF_TOKEN}"},
            json={"model": config.HF_MODEL, "max_tokens": max_tokens, "temperature": 0.2,
                  "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
            timeout=25,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return None
