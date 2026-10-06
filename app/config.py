"""Settings for InsightDesk, read from environment variables (and an optional .env file).

Every value is read at the moment it is used, so tests and eval/run_eval.py can change
an environment variable and the next call sees the new value without restarting.
"""
import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


# Load KEY=VALUE lines from .env into the environment once, without overriding real env vars.
def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


class Settings:
    """Each property reads its environment variable fresh, with a sensible default."""

    @property
    def MOCK_LLM(self) -> bool:
        return os.getenv("MOCK_LLM", "false").lower() in ("1", "true", "yes")

    @property
    def LLM_PROVIDER(self) -> str:
        return os.getenv("LLM_PROVIDER", "ollama")

    @property
    def OLLAMA_BASE_URL(self) -> str:
        return os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    @property
    def OLLAMA_MODEL(self) -> str:
        return os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct")

    @property
    def EMBED_MODEL(self) -> str:
        return os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")

    @property
    def TOP_K(self) -> int:
        return int(os.getenv("TOP_K", "3"))

    @property
    def CHROMA_DIR(self) -> str:
        return os.getenv("CHROMA_DIR", str(ROOT / ".chroma"))

    @property
    def SQLITE_PATH(self) -> str:
        return os.getenv("SQLITE_PATH", str(ROOT / "insightdesk.db"))

    # Web-app sign-in (app/auth.py). Empty DEMO_PASSWORD switches sign-in off; empty AUTH_SECRET means a
    # random key per process, so sessions end when the API restarts.
    @property
    def DEMO_PASSWORD(self) -> str:
        return os.getenv("DEMO_PASSWORD", "")

    @property
    def AUTH_SECRET(self) -> str:
        return os.getenv("AUTH_SECRET", "")

    @property
    def SESSION_HOURS(self) -> int:
        return int(os.getenv("SESSION_HOURS", "8"))

    @property
    def DATA_DIR(self) -> str:
        return os.getenv("DATA_DIR", str(ROOT / "data"))


settings = Settings()
