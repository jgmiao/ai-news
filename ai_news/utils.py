import os
import logging

def setup_logging():
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_name, logging.INFO)
    
    logging.basicConfig(
        level=level, 
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%H:%M:%S'
    )
    # Suppress noisy libraries (set to WARNING or ERROR)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("curl_cffi").setLevel(logging.WARNING)
    logging.getLogger("duckduckgo_search").setLevel(logging.WARNING)
    logging.getLogger("primp").setLevel(logging.WARNING)

def setup_proxy(config: dict):
    """Sets up system proxy"""
    proxy_conf = config.get("proxy", {})
    http_proxy = proxy_conf.get("http")
    https_proxy = proxy_conf.get("https")
    
    if http_proxy:
        os.environ["HTTP_PROXY"] = http_proxy
        logging.info(f"🌐 (HTTP) Proxy set to: {http_proxy}")
    if https_proxy:
        os.environ["HTTPS_PROXY"] = https_proxy
        logging.info(f"🌐 (HTTPS) Proxy set to: {https_proxy}")
