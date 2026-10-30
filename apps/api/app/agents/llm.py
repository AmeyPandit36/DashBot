"""Gemini access layer with deterministic fallbacks and optional Langfuse tracing.

The API key never leaves this process. When no key is configured the platform
runs in *deterministic mode*: semantic inference, SQL generation and narrative
composition use rule-based implementations over the same data. Nothing is
fabricated — every number still comes from DuckDB.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field
from typing import Any, TypeVar

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.core.logging import log_event

logger = logging.getLogger("agentic_bi.llm")
TModel = TypeVar("TModel", bound=BaseModel)

_STOPWORDS = set(
    """a an and are as at be by for from has have how in into is it its of on or our over that the their
    then there these this to was were what when where which who why will with you your me my we us do does
    did can could should would please show give tell list top between compare across per""".split()
)


@dataclass
class LLMResult:
    text: str = ""
    data: dict | None = None
    tokens: int = 0
    latency_ms: float = 0
    model: str = ""
    used_llm: bool = False
    error: str | None = None
    extra: dict = field(default_factory=dict)


def llm_available() -> bool:
    return settings.llm_configured


def _client():
    from google import genai

    return genai.Client(api_key=settings.GEMINI_API_KEY)


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
def _generate(prompt: str, system: str | None, temperature: float, json_mode: bool) -> tuple[str, int]:
    from google.genai import types

    client = _client()
    config = types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=system,
        response_mime_type="application/json" if json_mode else "text/plain",
        max_output_tokens=4096,
    )
    response = client.models.generate_content(model=settings.GEMINI_MODEL, contents=prompt, config=config)
    text = (response.text or "").strip()
    tokens = 0
    usage = getattr(response, "usage_metadata", None)
    if usage is not None:
        tokens = int(getattr(usage, "total_token_count", 0) or 0)
    return text, tokens


def generate(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.2,
    json_mode: bool = False,
    trace_name: str = "llm.call",
    trace_meta: dict | None = None,
) -> LLMResult:
    started = time.perf_counter()
    if not llm_available():
        return LLMResult(error="llm_not_configured", model="deterministic")
    try:
        text, tokens = _generate(prompt, system, temperature, json_mode)
        latency = round((time.perf_counter() - started) * 1000, 2)
        _trace(trace_name, {"prompt": prompt[:2000], "tokens": tokens, "latency_ms": latency, **(trace_meta or {})})
        return LLMResult(
            text=text,
            tokens=tokens,
            latency_ms=latency,
            model=settings.GEMINI_MODEL,
            used_llm=True,
        )
    except Exception as exc:  # noqa: BLE001 - degrade gracefully to deterministic mode
        log_event(logger, "gemini_call_failed", error=str(exc), trace=trace_name)
        return LLMResult(
            error=str(exc),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            model=settings.GEMINI_MODEL,
        )


def generate_structured(
    prompt: str,
    schema: type[TModel],
    *,
    system: str | None = None,
    temperature: float = 0.1,
    trace_name: str = "llm.structured",
) -> tuple[TModel | None, LLMResult]:
    result = generate(prompt, system=system, temperature=temperature, json_mode=True, trace_name=trace_name)
    if not result.text:
        return None, result
    raw = _extract_json(result.text)
    if raw is None:
        result.error = "invalid_json"
        return None, result
    try:
        parsed = schema.model_validate(raw)
        return parsed, result
    except Exception as exc:  # noqa: BLE001
        result.error = f"schema_validation_failed: {exc}"
        return None, result


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text.strip())
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------------------
# Embeddings
# ---------------------------------------------------------------------------
def _hash_embed(text: str, dim: int) -> list[float]:
    """Deterministic feature-hashing embedding used when no API key is present."""
    vector = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for token in tokens:
        if token in _STOPWORDS or len(token) < 2:
            continue
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        weight = 1.0 + math.log1p(len(token))
        vector[idx] += sign * weight
        # bigram signal for phrase matching
        bigram = digest[:2]
        vector[int.from_bytes(bigram, "big") % dim] += sign * 0.4
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [round(v / norm, 6) for v in vector]


def embed_texts(texts: list[str], *, trace_name: str = "embedding") -> tuple[list[list[float]], LLMResult]:
    if not texts:
        return [], LLMResult(model="deterministic")
    if llm_available():
        started = time.perf_counter()
        try:
            from google.genai import types

            client = _client()
            response = client.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=texts,
                config=types.EmbedContentConfig(output_dimensionality=settings.EMBEDDING_DIM),
            )
            vectors = [list(e.values) for e in response.embeddings]
            if len(vectors) == len(texts):
                latency = round((time.perf_counter() - started) * 1000, 2)
                _trace(trace_name, {"count": len(texts), "latency_ms": latency})
                return vectors, LLMResult(
                    model=settings.GEMINI_EMBEDDING_MODEL,
                    latency_ms=latency,
                    used_llm=True,
                    tokens=0,
                )
        except Exception as exc:  # noqa: BLE001
            log_event(logger, "gemini_embedding_failed", error=str(exc))
    return (
        [_hash_embed(t, settings.EMBEDDING_DIM) for t in texts],
        LLMResult(model="deterministic-hash", error="llm_not_configured" if not llm_available() else "embedding_failed"),
    )


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS and len(t) > 1]


def _trace(name: str, payload: dict[str, Any]) -> None:
    """Best-effort Langfuse ingestion; never blocks or fails a request."""
    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return
    try:
        import base64

        import httpx

        auth = base64.b64encode(
            f"{settings.LANGFUSE_PUBLIC_KEY}:{settings.LANGFUSE_SECRET_KEY}".encode()
        ).decode()
        event = {
            "batch": [{
                "id": hashlib.md5(f"{name}{time.time()}".encode()).hexdigest(),
                "type": "trace-create",
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
                "body": {"name": name, "metadata": payload},
            }]
        }
        httpx.post(
            f"{settings.LANGFUSE_HOST}/api/public/ingestion",
            json=event,
            headers={"Authorization": f"Basic {auth}"},
            timeout=1.5,
        )
    except Exception:  # noqa: BLE001 - observability must never break analytics
        return
