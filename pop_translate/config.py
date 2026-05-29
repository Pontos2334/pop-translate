import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".config", "pop-translate")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "api_key": "",
    "api_url": "https://api.deepseek.com/chat/completions",
    "model": "deepseek-chat",
    "timeout": 15,
}


class Config:
    def __init__(self):
        self.api_key = DEFAULTS["api_key"]
        self.api_url = DEFAULTS["api_url"]
        self.model = DEFAULTS["model"]
        self.timeout = DEFAULTS["timeout"]

    def load(self):
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("api_key"):
                    self.api_key = data["api_key"]
                if data.get("api_url"):
                    self.api_url = data["api_url"]
                if data.get("model"):
                    self.model = data["model"]
                if data.get("timeout"):
                    self.timeout = int(data["timeout"])
            except (json.JSONDecodeError, OSError):
                pass
        self._apply_env()

    def _apply_env(self):
        env_key = os.environ.get("POP_TRANSLATE_API_KEY", "")
        if env_key:
            self.api_key = env_key
        env_url = os.environ.get("POP_TRANSLATE_API_URL", "")
        if env_url:
            self.api_url = env_url
        env_model = os.environ.get("POP_TRANSLATE_MODEL", "")
        if env_model:
            self.model = env_model

    def save(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        data = {
            "api_key": self.api_key,
            "api_url": self.api_url,
            "model": self.model,
            "timeout": self.timeout,
        }
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    @property
    def has_api_key(self):
        return bool(self.api_key.strip())
