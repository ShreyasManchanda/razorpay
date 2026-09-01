import asyncio
import json
import logging

from langchain_core.messages import HumanMessage
from pydantic import ValidationError

from warden.config import settings

logger = logging.getLogger(__name__)


class LLMProviderChain:
    """Manages ordered fallback across LLM providers on rate-limit or connection errors.

    Order reflects real quota reality: TokenRouter (unlimited free) first,
    OpenRouter (MiniMax backup) second, Groq (rate-limited free tier) third,
    Gemini (credits exhausted) last.
    """

    def __init__(self):
        self.chain: list[dict] = []
        if settings.tokenrouter_api_key:
            self.chain.append(
                {
                    "provider": "tokenrouter",
                    "model": "qwen/qwen3.8-max-free",
                    "base_url": settings.tokenrouter_base_url,
                    "api_key": settings.tokenrouter_api_key,
                }
            )
        if settings.openrouter_api_key:
            self.chain.append(
                {
                    "provider": "openrouter",
                    "model": settings.openrouter_model,
                    "base_url": settings.openrouter_base_url,
                    "api_key": settings.openrouter_api_key,
                }
            )
        if settings.groq_api_key:
            self.chain.append({"provider": "groq", "model": "openai/gpt-oss-20b"})
        if settings.google_api_key:
            self.chain.append({"provider": "gemini", "model": "gemini-3.5-flash"})

    @property
    def available(self) -> bool:
        return len(self.chain) > 0

    def create(self, temperature: float = 0.5, model_override: str | None = None):
        """Return the first available provider's LLM instance. Raises if none configured."""
        if not self.chain:
            raise RuntimeError(
                "No LLM API key found. Set TOKENROUTER_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY, or GOOGLE_API_KEY in .env"
            )
        return self._build(self.chain[0], temperature, model_override)

    def structured_instances(
        self,
        temperature: float = 0.5,
        model_override: str | None = None,
        provider_order: tuple[str, ...] | None = None,
    ) -> list:
        """Materialize the provider chain once so all providers use one output contract."""
        configs = self.chain
        if provider_order:
            rank = {provider: index for index, provider in enumerate(provider_order)}
            configs = sorted(self.chain, key=lambda config: rank.get(config["provider"], len(rank)))
        return [self._build(c, temperature, model_override) for c in configs]

    def _build(self, config: dict, temperature: float, model_override: str | None):
        model = model_override or config["model"]
        provider = config["provider"]

        # Reasoning models (gpt-oss, qwen3.8, minimax-m3) can spend the default
        # token budget on hidden reasoning and return empty content, which the
        # structured-output wrapper then rejects as invalid. Give every provider
        # an explicit budget large enough for reasoning plus a small JSON object.
        if provider == "groq":
            from langchain_groq import ChatGroq

            return ChatGroq(
                model=model,
                groq_api_key=settings.groq_api_key,
                temperature=temperature,
                max_tokens=4096,
            )
        elif provider == "tokenrouter" or provider == "openrouter":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=model,
                openai_api_key=config["api_key"],
                openai_api_base=config["base_url"],
                temperature=temperature,
                max_tokens=4096,
            )
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=model,
                google_api_key=settings.google_api_key,
                temperature=temperature,
                max_output_tokens=4096,
            )
        else:
            raise ValueError(f"Unknown provider: {provider}")


RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (1.0, 4.0)


class FallbackStructured:
    """Structured-output wrapper with provider failover. Shared across all agents.

    Transient provider errors (capacity blips, per-minute rate limits) are retried
    against the same provider with short backoff before moving on — falling through
    instantly would burn limited daily quotas (e.g. OpenRouter free tier) on blips.
    """

    def __init__(self, instances: list, schema, *, retry_attempts: int | None = None):
        self.instances = instances
        self.schema = schema
        self.retry_attempts = max(1, RETRY_ATTEMPTS if retry_attempts is None else retry_attempts)

    def _is_retryable(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        # A drained prepaid account will not recover within a retry window.
        if "credits are depleted" in msg or "prepayment credits" in msg:
            return False
        keywords = (
            "rate limit",
            "429",
            "resource_exhausted",
            "connection error",
            "timeout",
            "overloaded",
            "403",
            "insufficient_user_quota",
            "credit limit is insufficient",
            "quota",
            "503",
            "502",
            "service unavailable",
            "server_selection_failed",
            "no available servers",
            "temporarily",
            "invalid structured output",
            "invalid json",
            "validation error",
            "missing required field",
        )
        return any(k in msg for k in keywords)

    @staticmethod
    def _extract_json(content) -> dict:
        # Some providers (reasoning models, multimodal APIs) return a list of parts.
        if isinstance(content, list):
            content = "".join(
                str(block.get("text", "")) if isinstance(block, dict) else str(block) for block in content
            )
        if not isinstance(content, str):
            raise ValueError("Invalid structured output: model content is not text")

        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:]

        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError(f"Invalid structured output: no JSON object in model response: {text[:200]}")
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON from model: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Invalid structured output: expected a JSON object")
        return parsed

    @staticmethod
    def _schema_prompt(schema) -> HumanMessage:
        properties = list(getattr(schema, "model_fields", {}).keys())
        fields = ", ".join(properties)
        return HumanMessage(
            content=(
                f"Return exactly one valid JSON object with these keys: {fields}. "
                "Do not use markdown, explanations, or any text outside the JSON object."
            )
        )

    async def ainvoke(self, messages, **kwargs):
        last_exc = None
        for i, llm in enumerate(self.instances):
            for attempt in range(self.retry_attempts):
                try:
                    prompt = list(messages) + [self._schema_prompt(self.schema)]
                    response = await llm.ainvoke(prompt, **kwargs)
                    data = self._extract_json(response.content)
                    return self.schema.model_validate(data)
                except (ValueError, ValidationError) as exc:
                    # Bad model output: retrying the same provider rarely helps.
                    last_exc = exc
                    logger.warning(f"Provider {i} returned invalid structured output.")
                    break
                except Exception as e:
                    if not self._is_retryable(e):
                        raise
                    last_exc = e
                    if attempt < self.retry_attempts - 1:
                        delay = RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)]
                        logger.warning(f"Provider {i} failed ({type(e).__name__}), retrying in {delay}s.")
                        await asyncio.sleep(delay)
                        continue
                    logger.warning(f"Provider {i} still failing after {self.retry_attempts} attempts.")
        raise last_exc or RuntimeError("All providers failed")


_chain_instance = None


def get_chain() -> LLMProviderChain:
    global _chain_instance
    if _chain_instance is None:
        _chain_instance = LLMProviderChain()
    return _chain_instance


def create_llm(temperature: float = 0.5, model_override: str | None = None):
    """Simple factory returning first available provider's LLM (no fallback)."""
    return get_chain().create(temperature=temperature, model_override=model_override)
