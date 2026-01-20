import time
import random
import logging
import warnings
import concurrent.futures
from typing import List, Dict, Any
from urllib.parse import quote
from datetime import datetime

# Suppress the "renamed to ddgs" warning from duckduckgo_search
# warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*renamed to.*ddgs.*")

import feedparser
from ddgs import DDGS
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from ai_news.utils import setup_proxy

# Define retry strategy with logging
def log_retry_attempt(retry_state):
    exception = retry_state.outcome.exception()
    ex_str = str(exception)
    # Generic friendly mapping
    if "Connection refused" in ex_str or "ProxyError" in ex_str:
        msg = "Network connection failed (Check Proxy/Internet)"
    elif "ReadTimeout" in ex_str:
        msg = "Request timed out"
    else:
        msg = ex_str
        
    # User requested: "Query exceptions, tell me it is retrying"
    if "timed out" in ex_str.lower():
         logging.debug(f"⏳ Timeout (Retrying...): {retry_state.fn.__name__}")
    else:
         logging.info(f"🔄 Connection Issue (Retrying...): {retry_state.fn.__name__} - {msg}")

retry_strategy = retry(
    stop=stop_after_attempt(3), 
    wait=wait_fixed(2),
    retry=retry_if_exception_type(Exception),
    before_sleep=log_retry_attempt
)

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_from_ddg(query: str, max_results: int, region: str = "wt-wt", timelimit: str = "d") -> List[dict]:
    """Generic DuckDuckGo search function"""
    results = []
    # Removed inner try-except to allow tenacity to catch and retry
    with DDGS() as ddgs:
        ddgs_gen = ddgs.news(
            query=query, 
            region=region, 
            safesearch="off", 
            timelimit=timelimit, 
            max_results=max_results
        )
        if ddgs_gen:
            results = list(ddgs_gen)
    return results

def fetch_google_news_rss(topic: str, config: Dict[str, Any]) -> List[dict]:
    """Fetch Google News via RSS"""
    results = []
    try:
        # Default to CN/zh-Hans if not specified, but flexible
        encoded_topic = quote(topic)
        rss_url = f"https://news.google.com/rss/search?q={encoded_topic}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
        logging.info(f"📡 Fetching Google News RSS: {rss_url}")
        
        feed = feedparser.parse(rss_url)
        
        for entry in feed.entries[:20]: # Limit to reasonable number
            results.append({
                "title": entry.title,
                "date": entry.published if 'published' in entry else datetime.now().isoformat(),
                "source": entry.source.title if 'source' in entry else "Google News",
                "url": entry.link,
                "body": entry.summary if 'summary' in entry else entry.title # RSS uses summary as snippet
            })
    except Exception as e:
        logging.error(f"❌ Google News RSS failed: {e}")
    
    return results

@retry_strategy
def fetch_ddg_general(topic: str, max_results: int, region: str, timelimit: str) -> List[dict]:
    # Jitter to avoid exact simultaneous hits
    time.sleep(random.uniform(0.5, 2.0))
    logging.info(f"🔍 [DuckDuckGo] Searching: '{topic}'...")
    try:
        results = fetch_from_ddg(topic, max_results, region, timelimit)
        logging.info(f"✅ [DuckDuckGo] Retrieved {len(results)} items.")
        return results
    except Exception as e:
        logging.warning(f"⚠️ [DuckDuckGo] Final failure after retries: {e}")
        return []

@retry_strategy
def fetch_ddg_domestic(name: str, site_query: str, topic: str, max_results: int, region: str, timelimit: str) -> List[dict]:
    # Jitter to avoid exact simultaneous hits
    time.sleep(random.uniform(0.5, 2.0))
    query = f"{topic} {site_query}"
    logging.info(f"🔍 [{name}] Searching: '{query}'...")
    
    try:
        # Still using a safe region for domestic, e.g. cn-zh
        results = fetch_from_ddg(query, 10, region="cn-zh", timelimit=timelimit)
        
        if not results:
            logging.warning(f"⚠️ [{name}] No results found. This might be due to rate limiting or strict filtering.")
        else:
            logging.info(f"✅ [{name}] Retrieved {len(results)} items.")
        return results
    except Exception as e:
         msg = str(e)
         if "ProxyError" in msg or "ConnectError" in msg or "ReadTimeout" in msg:
             logging.warning(f"⚠️ [{name}] Configured as 'domestic' but failed (DDG engine blocked). Proxy required even for '{site_query}'.")
         else:
             logging.warning(f"⚠️ [{name}] Final failure after retries: {e}")
         return []

def fetch_google_news_wrapper(topic: str, config: Dict[str, Any]) -> List[dict]:
    logging.info(f"🔍 [Google News] Searching: '{topic}'...")
    try: 
        results = fetch_google_news_rss(topic, config)
        logging.info(f"✅ [Google News] Retrieved {len(results)} items.")
        return results
    except Exception as e:
        logging.error(f"❌ [Google News] Failed: {e}")
        return []

def search_news(topic: str, config: Dict[str, Any], planned_tasks: Optional[List[Dict[str, Any]]] = None) -> List[dict]:
    # 0. Setup Proxy if not already handled generally, but okay to call again
    setup_proxy(config)

    search_conf = config.get("search", {})
    # Defaults
    timeout = search_conf.get("timeout", 60) 
    # Use hardcoded region/timelimit as per simplification request
    region = "wt-wt"
    timelimit = "d" 
    
    all_results = []
    tasks = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        
        # Branch 1: Execute AI Plan
        if planned_tasks:
            logging.info("🚀 Executing AI Search Plan...")
            for task in planned_tasks:
                source_name = task.get("source_name", "Unknown")
                source_type = task.get("source_type", "site_search")
                fetch_limit = task.get("fetch_limit", 10)
                search_query = task.get("search_query", "")
                
                if source_type == "google_news":
                    future = executor.submit(fetch_google_news_wrapper, topic, config)
                    tasks[future] = f"[Plan] {source_name}"
                    
                elif source_type == "duckduckgo_general":
                    future = executor.submit(fetch_ddg_general, topic, fetch_limit, region, timelimit)
                    tasks[future] = f"[Plan] {source_name}"
                    
                elif source_type == "site_search":
                    # For planned site search, search_query includes "site:..."
                    # We pass it to fetch_ddg_domestic. 
                    # Note: fetch_ddg_domestic expects "site_query" like "site:qq.com".
                    # Planner returns full query suffix e.g. "site:hupu.com".
                    future = executor.submit(fetch_ddg_domestic, source_name, search_query, topic, fetch_limit, region, timelimit)
                    tasks[future] = f"[Plan] {source_name}"
        
        # Branch 2: Static Config Fallback
        else:
            logging.info("⚙️  Executing Static Config Search...")
            # New Config Structure
            news_sources = search_conf.get("news_sources", {})
            
            # Iterate over groups (core, other)
            for group_name, group_conf in news_sources.items():
                if not group_conf.get("enabled", True):
                    continue
                
                items = group_conf.get("items", {})
                # Legacy fallback count if no planner
                group_fetch_count = 10 

                for source_key, source_conf in items.items():
                    if not source_conf.get("enabled", True):
                        continue
                    
                    # Determine Fetcher Type
                    
                    # 1. Google News RSS
                    if source_key == "google_news":
                        future = executor.submit(fetch_google_news_wrapper, topic, config)
                        tasks[future] = f"[{group_name}] Google News"
                    
                    # 2. DuckDuckGo General
                    elif source_key == "duckduckgo_search":
                        future = executor.submit(fetch_ddg_general, topic, group_fetch_count, region, timelimit)
                        tasks[future] = f"[{group_name}] DuckDuckGo"
                        
                    # 3. Site-Specific (Domestic) via DDG
                    elif "search_query" in source_conf:
                        # e.g. "site:qq.com"
                        site_query = source_conf["search_query"]
                        # Use match_names[0] as display name if available, else key
                        match_names = source_conf.get("match_names", [source_key])
                        display_name = match_names[0] if match_names else source_key
                        
                        # For domestic sources, use the configured fetch count (default 10 in logic or user config)
                        # Although we usually want fewer for domestic, respecting the group limit is cleaner.
                        # Or we can keep domestic specifically to 10 if not specified.
                        # Let's use group_fetch_count to be consistent with user config.
                        future = executor.submit(fetch_ddg_domestic, display_name, site_query, topic, group_fetch_count, region, timelimit)
                        tasks[future] = f"[{group_name}] {display_name}"
                    
                    else:
                        logging.warning(f"⚠️ Unknown source configuration for '{source_key}'. Skipping.")

        # Collect results with timeout
        # Calculate end time
        start_time = time.time()
        
        for future in concurrent.futures.as_completed(tasks):
            elapsed = time.time() - start_time
            remaining = timeout - elapsed
            
            source_name = tasks[future]
            try:
                # If remaining time is <= 0, we still give it a tiny moment or check if done
                if remaining < 0:
                    remaining = 0
                
                data = future.result(timeout=remaining)
                all_results.extend(data)
            except concurrent.futures.TimeoutError:
                logging.debug(f"⚠️ Fetching {source_name} timed out after {timeout} seconds. Skipping.")
                future.cancel() # Try to cancel
            except Exception as exc:
                msg = str(exc)
                if "ProxyError" in msg or "Connection refused" in msg or "ConnectError" in msg:
                    logging.warning(f"⚠️ [{source_name}] Connection Failed. If you are in China without a global proxy, this is expected for foreign sites.")
                else:
                    logging.error(f"❌ {source_name} generated an exception: {exc}")

    # 3. Deduplication (Simple URL based)
    seen_urls = set()
    unique_results = []
    for item in all_results:
        url = item.get("url")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(item)
    
    logging.info(f"📊 Total unique news items (by URL): {len(unique_results)}")

    # ==============================================================================
    # 3. Gap Fill (Compensation)
    # ==============================================================================
    search_conf = config.get("search", {})
    total_target = search_conf.get("total_news", 50)
    current_count = len(unique_results)
    gap = total_target - current_count
    
    if gap > 0:
        # Optimization: If we have > 90% of target (e.g. 45/50), or gap is small (< 3), just proceed.
        threshold = max(int(total_target * 0.9), total_target - 2)
        
        if current_count >= threshold:
             logging.info(f"✅ Quota nearly met ({current_count}/{total_target}). Proceeding with current results.")
        else:
             logging.warning(f"⚠️ Quota not met ({current_count}/{total_target}). Triggering fallback search for {gap} items...")
        try:
            # Use general search to fill the gap. Buffer slightly +2 to ensure robust fill.
            fill_count = gap + 2 
            fallback_results = fetch_ddg_general(topic, fill_count, region, timelimit)
            if fallback_results:
                logging.info(f"✅ Fallback search retrieved {len(fallback_results)} items.")
                
                # Dedup fallback results
                start_count = len(unique_results)
                for item in fallback_results:
                    url = item.get("url")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        unique_results.append(item)
                
                added = len(unique_results) - start_count
                logging.info(f"   (Actually added {added} new unique items)")
            else:
                logging.warning("⚠️ Fallback search returned no results.")
        except Exception as e:
            logging.error(f"❌ Fallback search failed: {e}")

    return unique_results
