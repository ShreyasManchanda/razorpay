from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_api_key: str = ""
    groq_api_key: str = ""
    tokenrouter_api_key: str = ""
    tokenrouter_base_url: str = "https://api.tokenrouter.com/v1"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "minimax/minimax-m3:free"
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()


def get_llm_provider() -> tuple[str, str]:
    """Returns (provider_name, model_name) based on available API keys."""
    if settings.tokenrouter_api_key:
        return "tokenrouter", "qwen/qwen3.8-max-free"
    if settings.openrouter_api_key:
        return "openrouter", settings.openrouter_model
    if settings.groq_api_key:
        return "groq", "openai/gpt-oss-20b"
    if settings.google_api_key:
        return "gemini", "gemini-3.5-flash"
    raise RuntimeError(
        "No LLM API key found. Set TOKENROUTER_API_KEY, OPENROUTER_API_KEY, GROQ_API_KEY, or GOOGLE_API_KEY in .env"
    )
