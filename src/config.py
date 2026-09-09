import os
import re
import yaml
from pathlib import Path
from dotenv import load_dotenv

def load_config(config_path: str = "config.yaml") -> dict:
    load_dotenv()

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path, "r") as f:
        content = f.read()

    # Replace ${ENV_VAR} placeholders
    def replace_env(match):
        env_var = match.group(1)
        return os.getenv(env_var, "")

    content_substituted = re.sub(r"\$\{([A-Za-z0-9_]+)\}", replace_env, content)
    config = yaml.safe_load(content_substituted)
    return config
