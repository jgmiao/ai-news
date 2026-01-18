import logging
import requests
import os
from typing import Dict, Tuple

def check_connectivity(config: Dict) -> Tuple[bool, str]:
    """
    Diagnose network connectivity.
    Returns: (is_global_access, message)
    """
    # Use proxy from env (already set by utils.setup_proxy) or config
    proxies = {}
    http_proxy = os.environ.get("HTTP_PROXY")
    https_proxy = os.environ.get("HTTPS_PROXY")
    if http_proxy: proxies["http"] = http_proxy
    if https_proxy: proxies["https"] = https_proxy

    # Targets to test
    # 1. Domestic (should always work)
    try:
        requests.get("https://www.baidu.com", timeout=3, proxies=proxies)
        logging.debug("✅ Domestic Network (Baidu) reachable.")
    except Exception as e:
        return False, "⚠️ Cannot access public internet (Baidu unreachable). Check local network."

    # 2. Global (Google) - Crucial for Google News / DDG
    try:
        requests.get("https://www.google.com", timeout=3, proxies=proxies)
        logging.debug("✅ Global Network (Google) reachable.")
        return True, "✅ Global network accessible."
    except Exception:
        # Try one more: GitHub
        try:
            requests.get("https://github.com", timeout=3, proxies=proxies)
            logging.debug("✅ Global Network (GitHub) reachable.")
            return True, "✅ Global network accessible (via GitHub)."
        except Exception:
            pass
    
    return False, "⚠️ Global network unreachable. Search engines (Google/DuckDuckGo) may fail."
