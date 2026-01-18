import os
import yaml
import logging
from typing import List, Dict, Any
# defines configuration loading logic
# Data models have been moved to ai_news/models.py

def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    if not os.path.exists(path):
        logging.error(f"❌ Config file not found: {path}")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
            logging.info(f"⚙️  Loaded config file: {path}")
            return config
    except Exception as e:
        logging.error(f"❌ Failed to read config file: {e}")
        return {}
