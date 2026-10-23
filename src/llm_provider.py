from __future__ import annotations

import json
import os
import random
import socket
import time
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class LLMHTTPError(RuntimeError):
    def __init__(self, code: int, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"LLM API error {code}: {detail[:700]}")


@dataclass
class LLMProvider:
    name: str = "mock"
    model: str | None = None
    last_model: str | None = None
    last_finish_reason: str | None = None

    @classmethod
    def from_env(cls, override: str | None = None) -> "LLMProvider":
        name = (override or os.getenv("LLM_PROVIDER", "gemini")).strip().lower()
        if name == "gemini":
            model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        elif name == "ollama":
            model = os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "llama3.2")).strip()
        else:
            model = (os.getenv("LLM_MODEL") or "").strip() or None
        return cls(name=name, model=model)

    @property
    def enabled(self) -> bool:
        if self.name == "gemini":
            return bool(os.getenv("GEMINI_API_KEY"))
        if self.name == "anthropic":
            return bool(os.getenv("ANTHROPIC_API_KEY") and self.model)
        if self.name == "openai":
            return bool(os.getenv("OPENAI_API_KEY") and self.model)
        if self.name == "ollama":
            return bool(self.model)
        return False

    @property
    def configured(self) -> bool:
        return self.enabled

    def generate(self, prompt: str, *, temperature: float = 0.2, max_tokens: int = 1200) -> str:
        if self.name == "gemini":
            return self._gemini(prompt, temperature=temperature, max_tokens=max_tokens)
        if self.name == "anthropic":
            return self._anthropic(prompt, temperature=temperature, max_tokens=max_tokens)
        if self.name == "openai":
            return self._openai(prompt, temperature=temperature, max_tokens=max_tokens)
        if self.name == "ollama":
            return self._ollama(prompt)
        raise RuntimeError("No remote LLM is configured")

    def generate_json(self, prompt: str, schema: dict[str, Any], *, temperature: float = 0.1, max_tokens: int = 1800) -> dict[str, Any]:
        """Generate a JSON object with one bounded repair pass for malformed model output.

        Gemini is requested in structured-output mode. In practice a response can still be
        unusable when it is truncated or a transient model glitch occurs. Rather than failing
        the whole research job immediately, do one short schema-constrained repair pass.
        """
        if self.name == "gemini":
            text = self._gemini(prompt, temperature=temperature, max_tokens=max_tokens, schema=schema)
            try:
                return self._parse_json(text)
            except (RuntimeError, json.JSONDecodeError) as first_exc:
                # Keep the repair prompt deliberately small. The malformed response is public
                # company research data, not user secrets, and is capped to avoid huge retries.
                repair_input = text.strip()[:12000]
                repair_prompt = (
                    "Repair the following model output into ONE valid JSON object that exactly "
                    "matches the provided response schema. Preserve only information already "
                    "present in the output. Do not add commentary or markdown.\n\n"
                    "BROKEN OUTPUT:\n" + repair_input
                )
                try:
                    repaired = self._gemini(
                        repair_prompt,
                        temperature=0.0,
                        max_tokens=max(max_tokens, 2600),
                        schema=schema,
                    )
                    return self._parse_json(repaired)
                except Exception as repair_exc:
                    raise RuntimeError(
                        "Structured output could not be parsed after one automatic repair attempt. "
                        f"Initial error: {type(first_exc).__name__}; repair error: {type(repair_exc).__name__}: {str(repair_exc)[:240]}"
                    ) from repair_exc
        text = self.generate(prompt + "\n\nReturn valid JSON only. Do not use markdown fences.", temperature=temperature, max_tokens=max_tokens)
        return self._parse_json(text)

    def _gemini_models(self) -> list[str]:
        primary = self.model or "gemini-3.8-flash"
        raw = os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite")
        models: list[str] = []
        for item in [primary, *raw.split(",")]:
            m = item.strip()
            if m and m not in models:
                models.append(m)
        return models

    def _gemini(self, prompt: str, *, temperature: float, max_tokens: int, schema: dict[str, Any] | None = None) -> str:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("The analysis engine is not configured. Set the API key in .env")

        generation_config: dict[str, Any] = {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        }
        if schema:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = schema
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config,
        }

        # Portfolio UX should fail fast instead of leaving the browser at 50% for minutes.
        # Google recommends bounded retries/backoff for transient 429/5xx responses;
        # we additionally enforce a hard wall-clock deadline across all model attempts.
        retries = max(1, int(os.getenv("GEMINI_RETRIES_PER_MODEL", "1")))
        request_timeout = max(3.0, float(os.getenv("GEMINI_REQUEST_TIMEOUT_SECONDS", "12")))
        total_deadline = max(request_timeout, float(os.getenv("GEMINI_TOTAL_DEADLINE_SECONDS", "32")))
        transient_codes = {408, 429, 500, 502, 503, 504}
        failures: list[str] = []
        deadline_at = time.monotonic() + total_deadline

        for model in self._gemini_models():
            if time.monotonic() >= deadline_at:
                break
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            for attempt in range(retries):
                remaining = deadline_at - time.monotonic()
                if remaining <= 0:
                    break
                timeout = max(1.0, min(request_timeout, remaining))
                try:
                    data = self._post_json_once(url, payload, {"x-goog-api-key": api_key}, timeout=timeout)
                    candidates = data.get("candidates") or []
                    if not candidates:
                        feedback = data.get("promptFeedback") or {}
                        raise RuntimeError(f"The analysis engine returned no candidate: {feedback}")
                    candidate = candidates[0]
                    finish_reason = str(candidate.get("finishReason") or "").strip()
                    self.last_finish_reason = finish_reason or None
                    parts = ((candidate.get("content") or {}).get("parts") or [])
                    text = "".join(str(p.get("text", "")) for p in parts if p.get("text"))
                    if not text.strip():
                        raise RuntimeError(f"The analysis engine returned an empty text response (finishReason={finish_reason or 'unknown'})")
                    # A schema-constrained response cut off by MAX_TOKENS is guaranteed to be
                    # risky to parse. Retry once on the same model with a larger output budget
                    # while respecting the overall wall-clock deadline.
                    if finish_reason == "MAX_TOKENS" and max_tokens < 4200 and time.monotonic() < deadline_at:
                        larger_config = dict(generation_config)
                        larger_config["maxOutputTokens"] = min(4200, max_tokens + 1600)
                        larger_payload = {
                            "contents": payload["contents"],
                            "generationConfig": larger_config,
                        }
                        remaining2 = deadline_at - time.monotonic()
                        if remaining2 > 1.0:
                            data2 = self._post_json_once(
                                url, larger_payload, {"x-goog-api-key": api_key},
                                timeout=max(1.0, min(request_timeout, remaining2)),
                            )
                            candidates2 = data2.get("candidates") or []
                            if candidates2:
                                c2 = candidates2[0]
                                self.last_finish_reason = str(c2.get("finishReason") or "").strip() or None
                                parts2 = ((c2.get("content") or {}).get("parts") or [])
                                text2 = "".join(str(p.get("text", "")) for p in parts2 if p.get("text"))
                                if text2.strip():
                                    text = text2
                    self.last_model = model
                    self.model = model
                    return text.strip()
                except LLMHTTPError as exc:
                    failures.append(f"{model}:HTTP {exc.code}")
                    if exc.code not in transient_codes:
                        raise
                    if attempt < retries - 1 and time.monotonic() < deadline_at:
                        delay = min(2.5, 0.8 * (2 ** attempt) + random.uniform(0.1, 0.35))
                        time.sleep(min(delay, max(0.0, deadline_at - time.monotonic())))
                        continue
                    break
                except TimeoutError:
                    failures.append(f"{model}:timeout")
                    break
                except RuntimeError as exc:
                    # Connection timeouts from urllib are transient; other runtime errors
                    # (bad JSON, blocked prompts, etc.) should still surface immediately.
                    text = str(exc).lower()
                    if "timed out" in text or "timeout" in text or "connection error" in text:
                        failures.append(f"{model}:network-timeout")
                        break
                    raise

        tried = ", ".join(self._gemini_models())
        details = ", ".join(failures[-8:]) or "deadline reached"
        raise RuntimeError(
            "The analysis engine did not respond within the app's research deadline or was temporarily unavailable. "
            f"Tried: {tried}. Attempts: {details}. "
            "Source pages were kept. Wait a moment and use 'Re-analyze saved' — the website will not be crawled again."
        )

    def _anthropic(self, prompt: str, *, temperature: float, max_tokens: int) -> str:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        model = self.model
        if not api_key or not model:
            raise RuntimeError("Set ANTHROPIC_API_KEY and LLM_MODEL")
        payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "messages": [{"role": "user", "content": prompt}]}
        data = self._post_json_once("https://api.anthropic.com/v1/messages", payload, {"x-api-key": api_key, "anthropic-version": "2023-06-01"})
        return data["content"][0]["text"]

    def _openai(self, prompt: str, *, temperature: float, max_tokens: int) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        model = self.model
        if not api_key or not model:
            raise RuntimeError("Set OPENAI_API_KEY and LLM_MODEL")
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        payload = {"model": model, "temperature": temperature, "max_tokens": max_tokens, "messages": [{"role": "user", "content": prompt}]}
        data = self._post_json_once(f"{base}/chat/completions", payload, {"Authorization": f"Bearer {api_key}"})
        return data["choices"][0]["message"]["content"]

    def _ollama(self, prompt: str) -> str:
        model = self.model or os.getenv("OLLAMA_MODEL")
        if not model:
            raise RuntimeError("Set OLLAMA_MODEL")
        url = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
        payload = {"model": model, "stream": False, "messages": [{"role": "user", "content": prompt}]}
        data = self._post_json_once(url, payload)
        return data["message"]["content"]

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].lstrip()
        try:
            value = json.loads(cleaned)
        except json.JSONDecodeError:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                raise RuntimeError("LLM did not return valid JSON")
            value = json.loads(cleaned[start:end + 1])
        if not isinstance(value, dict):
            raise RuntimeError("LLM JSON response was not an object")
        return value

    @staticmethod
    def _post_json_once(url: str, payload: dict, headers: dict[str, str] | None = None, *, timeout: float = 20.0) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise LLMHTTPError(exc.code, detail) from exc
        except (TimeoutError, socket.timeout) as exc:
            raise TimeoutError(f"LLM request timed out after {timeout:.0f}s") from exc
        except error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise TimeoutError(f"LLM request timed out after {timeout:.0f}s") from exc
            raise RuntimeError(f"LLM connection error: {reason}") from exc
