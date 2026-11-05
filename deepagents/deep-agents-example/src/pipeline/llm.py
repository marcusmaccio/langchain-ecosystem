import json
import os
import re
from typing import Optional
import requests
from langchain_openai import ChatOpenAI


def check_lm_studio_health(base_url: str, timeout: float = 3.0) -> bool:
    """Verifies that the local LM Studio daemon is active and responsive."""
    health_endpoint = f"{base_url.rstrip('/')}/models"
    try:
        response = requests.get(health_endpoint, timeout=timeout)
        if response.status_code == 200:
            models_data = response.json().get("data", [])
            loaded_ids = [m.get("id") for m in models_data]
            print(f"[OK] LM Studio active at {base_url}. Loaded: {loaded_ids}")
            return True
        return False
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return False


def get_resilient_lm_studio_client(
    primary_url: Optional[str] = None,
    fallback_url: Optional[str] = None,
    model_name: Optional[str] = None,
    response_format: Optional[dict] = None,
) -> ChatOpenAI:
    """Connects to primary localhost endpoint or falls back to LAN IP."""
    env_url = os.getenv("LM_STUDIO_BASE_URL")
    primary = primary_url or env_url or "http://localhost:1234/v1"
    fallback = fallback_url or os.getenv("LM_STUDIO_FALLBACK_URL", "http://192.168.1.21:1234/v1")
    model = model_name or os.getenv("LM_STUDIO_MODEL", "qwen3.8-27b-uncensored-mlx")

    target_url = primary
    if not check_lm_studio_health(target_url):
        print(f"[WARN] Failed connecting to {primary}. Testing fallback: {fallback}")
        if check_lm_studio_health(fallback):
            target_url = fallback
        else:
            raise ConnectionError(
                f"LM Studio offline at both {primary} and {fallback}. "
                "Ensure LM Studio Local Server is started with CORS enabled."
            )

    model_kwargs = {}
    # LM Studio 0.3+ rejects {"type": "json_object"} with 400 unless configured.
    # Allow overriding via env or argument.
    resp_format_env = os.getenv("LM_STUDIO_RESPONSE_FORMAT")
    if response_format is not None:
        model_kwargs["response_format"] = response_format
    elif resp_format_env:
        try:
            model_kwargs["response_format"] = json.loads(resp_format_env)
        except Exception:
            model_kwargs["response_format"] = {"type": resp_format_env}

    timeout = float(os.getenv("LM_STUDIO_TIMEOUT", "180.0"))
    return ChatOpenAI(
        base_url=target_url,
        api_key=os.getenv("LM_STUDIO_API_KEY", "not-needed"),
        model=model,
        temperature=0.1,
        request_timeout=timeout,
        max_retries=1,
        model_kwargs=model_kwargs
    )


def extract_json_from_response(content: str) -> str:
    """Strips thinking blocks, markdown fences, and leading/trailing whitespace."""
    content = content.strip()
    # Strip <think>...</think> reasoning blocks if present
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    # Strip markdown code blocks
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return content
