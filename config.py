import json
import os

CONFIG_DIR = os.path.expanduser("~/.config/jarvis")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


def save_config(config: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def get_api_key() -> str | None:
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    config = load_config()
    return config.get("groq_api_key")


def set_api_key(key: str):
    config = load_config()
    config["groq_api_key"] = key
    save_config(config)
