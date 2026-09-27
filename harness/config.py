"""Submission configuration. Credentials are runtime-only, never loaded from files."""
from dataclasses import dataclass, field
import os
from pathlib import Path

from .api_adapter import configuration


@dataclass(frozen=True)
class Settings:
    provider: str = "deepseek"
    model: str = "deepseek-v4-pro"
    base: str = "https://api.deepseek.com"
    key: str = field(default="", repr=False)
    data: Path = field(default_factory=lambda: Path.home() / ".local/share/rakshak/runs")
    tokens: int = 12000
    attempts: int = 5

    @classmethod
    def from_env(cls, env=None):
        env = os.environ if env is None else env
        result = cls(provider=env.get("AI_PROVIDER", "deepseek"),
                     model=env.get("AI_MODEL", "deepseek-v4-pro"),
                     base=env.get("AI_BASE_URL", "https://api.deepseek.com"),
                     key=env.get("AI_API_KEY", ""),
                     data=Path(env.get("HARNESS_DATA_DIR", str(Path.home() / ".local/share/rakshak/runs"))).expanduser(),
                     tokens=int(env.get("HARNESS_TOKENS", "12000")),
                     attempts=int(env.get("HARNESS_ATTEMPTS", "5")))
        if not 1000 <= result.tokens <= 200000 or not 1 <= result.attempts <= 20:
            raise ValueError("HARNESS_TOKENS must be 1000-200000; HARNESS_ATTEMPTS must be 1-20")
        # Validate public settings even if the evaluator has not supplied a key yet.
        configuration(result.provider, result.base, result.model, result.key or "validation-only")
        return result

    def connect(self, store):
        if not self.key:
            raise ValueError("AI_API_KEY is missing. Export it in the launching terminal, then restart make run.")
        return store.configure({"provider": self.provider, "api_base": self.base,
                                "model": self.model, "api_key": self.key})
