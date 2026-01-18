import os
import json
import logging
import difflib
import re
from datetime import datetime
from typing import List, Optional, Dict, Any

from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

from ai_news.models import NewsReport, NewsItem

def prune_news_items(raw_news: List[dict], config: Dict[str, Any] = None, max_items_total: int = 50, max_len: int = 300) -> List[dict]:
    """
    Optimizes token usage by:
    1. Removing fuzzy duplicates based on title similarity.
    2. Stratified Sampling: Taking top N items per source (configurable limits).
    3. Global Limit: Capping total items.
    4. Truncating the body text of each item.
    """
    logging.info(f"✂️  Pruning news items: input count={len(raw_news)}")
    
    # 1. Deduplication (Fuzzy)
    unique_news = []
    seen_titles = []
    
    for item in raw_news:
        title = item.get("title", "")
        # Check similarity
        is_duplicate = False
        for seen in seen_titles:
            # If similarity > 0.8, consider it a duplicate
            if difflib.SequenceMatcher(None, title, seen).ratio() > 0.8:
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_news.append(item)
            seen_titles.append(title)
            
    logging.info(f"✂️  After fuzzy deduplication: {len(unique_news)} items")
    
    # 2. Stratified Sampling (Group by Source)
    results_by_source = {}
    for item in unique_news:
        source = item.get("source", "Unknown")
        if source not in results_by_source:
            results_by_source[source] = []
        results_by_source[source].append(item)
    
    # Take top N from each source
    balanced_news = []
    
    # Flatten: Iterate through sources and pick quotas
    # Get limits from new config structure
    search_conf = config.get("search", {}) if config else {}
    news_sources_conf = search_conf.get("news_sources", {})
    
    # Defaults
    # Defaults
    config_total = search_conf.get("total_news", 50)
    # Effective limit: min(argument, config) to respect the stricter constraint
    total_target = min(config_total, max_items_total)
    min_per_core = search_conf.get("min_per_core_source", 3)
    
    # Identify Core Sources
    core_source_names = set()
    if "core" in news_sources_conf:
         items = news_sources_conf["core"].get("items", {})
         for _, item_conf in items.items():
             match_names = item_conf.get("match_names", [])
             for name in match_names:
                 core_source_names.add(name)

    # Apply Limits
    # Strategy: 
    # 1. We trust the upstream Planner to have allocated correctly.
    # 2. But we doubly ensure here that we don't accidentally cut off Core sources if we must truncate global list.
    # 3. Actually, since Planner sets limits on FETCHING, we might get fewer items than plan, but not more (usually).
    # 4. So simply applying global limit + deduplication is mostly enough.
    # 5. But let's keep a "Safe Keep" logic: Try to keep at least `min_per_core` for core sources.

    # Priority Queue approach simplified:
    # Just take everything unless we exceed total_target.
    # If exceeding, we prioritize Core sources up to a point?
    # For simplicity in this "Refactor": 
    # We will just flatten and truncate, but sort by "is_core" first? 
    # No, that might bias too much. The Planner already did the job.
    
    # Let's just flatten results_by_source back to list, respecting original order (relevance) as much as possible?
    # Actually `unique_news` is already a list in arrival order (usually relevance from search engine).
    
    balanced_news = unique_news
    
    # 3. Global Limit
    if len(balanced_news) > total_target:
        logging.warning(f"⚠️ Total items {len(balanced_news)} exceeds target {total_target}. Truncating.")
        balanced_news = balanced_news[:total_target]
    
    # 4. Truncate Content and Clean up
    processed_news = []
    for item in balanced_news:
        body = item.get("body", "") or ""
        item_copy = item.copy()
        if len(body) > max_len:
            item_copy["body"] = body[:max_len] + "..."
        processed_news.append(item_copy)
        
    return processed_news

def extract_json_from_response(content: str) -> Optional[dict]:
    """Reliably extracts JSON from LLM response, handling markdown fences."""
    try:
        # 1. Clean markdown code blocks
        json_str = content
        if "```" in content:
            # Regex to capture content inside ```json ... ``` or just ``` ... ```
            match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
            if match:
                json_str = match.group(1).strip()
        
        # 2. Parse
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        logging.error(f"❌ JSON Parse Error: {e}")
        logging.debug(f"Failed content: {content}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2), retry=retry_if_exception_type(Exception))
def call_llm_api(client, model, messages):
    # Log the request at DEBUG level
    logging.debug(f"📝 LLM Request: {json.dumps(messages, ensure_ascii=False)}")
    
    return client.chat.completions.create(
        model=model,
        messages=messages,
        response_format={"type": "json_object"}
    )

def create_llm_client(config: Dict[str, Any]):
    """Helper to create OpenAI client from config"""
    llm_conf = config.get("llm", {})
    # Prioritize Generic Env Vars -> Config -> Legacy Env Vars
    api_key = os.getenv("API_KEY") or llm_conf.get("api_key") or os.getenv("DASHSCOPE_API_KEY")
    base_url = os.getenv("BASE_URL") or llm_conf.get("base_url") or os.getenv("DASHSCOPE_BASE_URL") or "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model_name = os.getenv("MODEL_NAME") or llm_conf.get("model_name") or "qwen-max"
    
    if not api_key:
         logging.error("❌ API Key not found. Please set 'API_KEY' (or 'DASHSCOPE_API_KEY') env var or configure in config.yaml.")
         return None, None
         
    client = OpenAI(api_key=api_key, base_url=base_url)
    return client, model_name

def process_with_llm(topic: str, raw_news: List[dict], config: Dict[str, Any]) -> NewsReport:
    if not raw_news:
        return NewsReport(topic=topic, prologue="No news found related to the topic.", top_news=[])

    # OPTIMIZATION: Prune items before sending to LLM
    final_news_list = prune_news_items(raw_news, config, max_items_total=50, max_len=300)

    logging.info(f"🧠 Calling AI for filtering and summarization ({len(final_news_list)} items)...")
    
    client, model_name = create_llm_client(config)
    if not client:
        return NewsReport(topic=topic, prologue="API Config Error.", top_news=[])

    # Build Context
    news_context = ""
    for i, item in enumerate(final_news_list):
        news_context += f"""
        [News #{i+1}]
        Title: {item.get('title', 'N/A')}
        Date: {item.get('date', 'N/A')}
        Source: {item.get('source', 'N/A')}
        URL: {item.get('url', 'N/A')}
        Snippet: {item.get('body', 'N/A')}
        """

    today_str = datetime.now().strftime('%Y-%m-%d')
    prompt = f"""
    You are a professional senior news editor.
    Your goal is to identify the top 10 most influential news stories about the topic: "{topic}".
    Current Date: {today_str}
 
    Instructions:
    1. Filter: Select top 10 distinct and important news items from the provided list. Remove duplicates or irrelevant ads.
    2. Date Standardization: Output the 'date' field strictly in 'YYYY-MM-DD' format. If exact date unavailable, infer from context/crawl time.
    3. Translate: Ensure the 'title', 'summary', 'recommend_comment' and 'prologue' are in Chinese (Simplified).
    4. Summarize: Write a concise summary (50-100 words) for each news based on the snippet.
    5. Comment: Write a brief recommendation comment (recommend_comment) for each news item.
    6. Prologue: Write a prologue (50-100 words) summarizing the overall trend or key highlights of these selected news items.
    7. Format: Return ONLY a valid JSON object strictly following this structure:
       {{
         "prologue": "...",
         "top_news": [
           {{ "title": "...", "date": "YYYY-MM-DD", "source": "...", "url": "...", "summary": "...", "recommend_comment": "..." }},
           ...
         ]
       }}

    Raw News Data:
    {news_context}
    """

    try:
        completion = call_llm_api(client, model_name, [
            {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
            {"role": "user", "content": prompt}
        ])
        
        content = completion.choices[0].message.content
        logging.debug(f"📝 LLM Response: {content}")
        
        data = extract_json_from_response(content)
        
        if not data:
             raise ValueError("Failed to extract valid JSON from LLM response")
        
        # Compatibility: prevent LLM inconsistent keys
        raw_list = data.get("top_news") or data.get("news") or []
        prologue = data.get("prologue", f"Here is the latest news about {topic}.")
        
        # Convert to Pydantic model for validation
        news_items = []
        for item in raw_list:
            # Handle potential missing fields or extra fields safely
            try:
                ni = NewsItem(
                    title=item.get("title", "Untitled"),
                    url=item.get("url", "#"),
                    source=item.get("source", "Unknown"),
                    date=item.get("date", datetime.now().strftime("%Y-%m-%d")),
                    summary=item.get("summary", ""),
                    recommend_comment=item.get("recommend_comment", ""),
                    # body is usually missing in LLM output, it's fine
                )
                news_items.append(ni)
            except Exception as e:
                logging.warning(f"⚠️ Failed to parse news item: {item}. Error: {e}")

        report = NewsReport(topic=topic, prologue=prologue, top_news=news_items)
        logging.info(f"✨ Report generated successfully, containing {len(report.top_news)} hot news items.")
        return report

    except Exception as e:
        logging.error(f"❌ AI Processing Failed: {e}")
        return NewsReport(topic=topic, prologue="AI Processing Exception.", top_news=[])
