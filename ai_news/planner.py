import json
import logging
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from ai_news.processor import call_llm_api, create_llm_client
# from ai_news.config import NewsItem  <-- Removed unused import

class SearchTask(BaseModel):
    source_name: str = Field(description="Display name of the news source")
    search_query: str = Field(description="Specific search query (e.g., 'site:example.com topic') or blank for general search")
    fetch_limit: int = Field(description="Number of items to fetch from this source")
    source_type: str = Field(description="Type of source: 'google_news', 'duckduckgo_general', 'site_search'")

class SearchPlan(BaseModel):
    tasks: List[SearchTask]

def plan_search(topic: str, config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Uses LLM to plan the search strategy:
    1. Identifies relevant dynamic sources (vertical domains).
    2. Allocates fetch quotas to Fixed Sources (from config) and Dynamic Sources.
    """
    
    search_conf = config.get("search", {})
    # Determine total and safety limits
    user_target = search_conf.get("total_news", 50)
    # INFLATION: Request 1.5x items to account for dedup and failures
    planning_target = int(user_target * 1.5)
    
    min_per_core = search_conf.get("min_per_core_source", 3)
    
    # 1. Collect Fixed Sources from Config
    fixed_sources_description = []
    news_sources = search_conf.get("news_sources", {})
    
    # helper to format source info
    def add_source_info(group_name, items):
        for key, conf in items.items():
            if not conf.get("enabled", True):
                continue
            name = conf.get("match_names", [key])[0]
            stype = "google_news" if key == "google_news" else ("duckduckgo_general" if key == "duckduckgo_search" else "site_search")
            squery = conf.get("search_query", "")
            fixed_sources_description.append(
                f"- Name: {name}, Group: {group_name}, Type: {stype}, SearchQuerySuffix: '{squery}'"
            )

    if "core" in news_sources:
        add_source_info("core", news_sources["core"].get("items", {}))
    if "other" in news_sources:
        add_source_info("other", news_sources["other"].get("items", {}))

    fixed_sources_text = "\n".join(fixed_sources_description)

    # 2. Construct Prompt
    prompt = f"""
    You are an expert News Search Planner.
    The user wants to find news about: "{topic}"
    
    **Budget Constraints**:
    - Total News Budget: {planning_target} items (Optimized for coverage).
    - Core Source Guarantee: Each "Core" source MUST be allocated at least {min_per_core} items.
    
    **Goal**:
    1. **Fixed Sources**: Assign quotas to the fixed sources listed below.
    2. **Dynamic Sources**: Discover 3-5 high-quality "site:..." sources relevant to the topic (e.g., hupu.com for sports, github.com for tech).
    3. **Allocation Strategy**:
       - Reserve {min_per_core} items for each Core source.
       - Calculate remaining budget: Total - (NumCore * {min_per_core}).
       - Distribute the remaining budget to the most relevant sources (can be specific Core sources or new Dynamic sources).
       - Ensure the specific "other" generic sources (like DuckDuckGo) get some quota if specific sites are sparse.
    
    **Fixed Sources Pool**:
    {fixed_sources_text}
    
    **Output Format**:
    Return strictly a JSON object with a single key "tasks" containing a list of search tasks.
    Each task must have:
    - "source_name": Display name.
    - "source_type": One of "google_news", "duckduckgo_general", "site_search".
    - "search_query": 
        - For "site_search", MUST result in "site:domain.com". (e.g. "site:hupu.com"). 
        - For "fixed sources", use the suffix provided in description (if any).
        - For "google_news" or "duckduckgo_general", leave empty string "".
    - "fetch_limit": Integer quota.

    Return ONLY the JSON. No preamble.
    """

    logging.info(f"🧠 [Planner] Planning search for '{topic}' (BufferSize: {planning_target}, UserTarget: {user_target})...")
    
    try:
        client, model_name = create_llm_client(config)
        if not client:
            return []

        completion = call_llm_api(client, model_name, [
             {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
             {"role": "user", "content": prompt}
        ])
        
        response_text = completion.choices[0].message.content
        if not response_text:
            logging.error("❌ [Planner] LLM returned empty response.")
            return []

        # Extract JSON (handling potential markdown fences)
        json_clean = response_text.strip()
        if "```" in json_clean:
            import re
            match = re.search(r"```(?:json)?\s*(.*?)```", json_clean, re.DOTALL)
            if match:
                json_clean = match.group(1).strip()
        
        plan_data = json.loads(json_clean)
        tasks = plan_data.get("tasks", [])
        
        logging.info(f"✅ [Planner] Generated {len(tasks)} tasks.")
        valid_tasks = []
        for t in tasks:
            # Validate with Pydantic (optional but good for sanitization)
            try:
                # Ensure defaults
                if "search_query" not in t: t["search_query"] = ""
                
                # Logging
                logging.debug(f"    - {t.get('source_name')} ({t.get('source_type')}): Limit {t.get('fetch_limit')}, Query '{t.get('search_query')}'")
                valid_tasks.append(t)
            except Exception as e:
                 logging.warning(f"⚠️ Invalid task structure: {t}")

        return valid_tasks

    except Exception as e:
        logging.error(f"❌ [Planner] Planning failed: {e}")
        return []
