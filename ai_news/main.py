import os
import json
import logging
import argparse
from datetime import datetime

from ai_news.config import load_config
from ai_news.utils import setup_logging
from ai_news.search import search_news
from ai_news.planner import plan_search
from ai_news.models import NewsReport
from ai_news.processor import process_with_llm
from ai_news.renderer import generate_html



def main():
    # Setup Logging
    setup_logging()
    from ai_news import __version__
    logging.info(f"🚀 Starting AI News Integrator v{__version__}")
    
    # Load Config
    config = load_config()
    if not config:
        logging.warning("⚠️  Cannot load config file. Exiting.")
        return

    # Update Log Level from Config
    output_conf = config.get("output", {})
    config_log_level = output_conf.get("log_level")
    if config_log_level:
        logging.getLogger().setLevel(config_log_level.upper())

    # --- Network Self-Diagnosis ---
    from ai_news.utils import setup_proxy
    setup_proxy(config) # Setup proxy first for check
    
    from ai_news.diagnostics import check_connectivity
    is_global, msg = check_connectivity(config)
    if not is_global:
        logging.warning("-" * 50)
        logging.warning(f"⚠️  {msg}")
        logging.warning("   Results may be empty because Google/DuckDuckGo are blocked.")
        logging.warning("   Please configure 'proxy' in config.yaml for foreign sources.")
        logging.warning("-" * 50)
    else:
        logging.info(f"{msg}")
    # ------------------------------

    parser = argparse.ArgumentParser(description="Smart News Collector")
    parser.add_argument("topic", nargs="?", help="News topic (e.g. 'AI Agent')")
    parser.add_argument("--output", "-o", help="Output directory for markdown files")
    args = parser.parse_args()

    # Get keyword: CLI args > Env Var > Interactive Input
    topic = args.topic
    if not topic:
        topic = os.getenv("NEWS_TOPIC")
        if not topic:
            try:
                topic = input("Please enter news keyword (e.g. 'AI Agent'): ").strip()
            except EOFError:
                logging.error("Cannot get input")
                return

    if not topic:
        logging.warning("No keyword provided. Exiting.")
        return

    # Execute Flow
    # 1. Search News
    # Try Planning First
    planned_tasks = plan_search(topic, config)
    if planned_tasks:
        logging.info("🧠 Planner generated a dynamic search strategy.")
    
    raw_results = search_news(topic, config, planned_tasks)
    if not raw_results:
        logging.error("❌ No news found.")
        if not is_global:
            logging.warning("💡 Hint: You seem to be offline or in a restricted network. Configure 'proxy' in config.yaml.")
        print(json.dumps({"error": "No news found", "cause": "Network/Proxy" if not is_global else "Unknown"}, ensure_ascii=False))
        return

    final_report = process_with_llm(topic, raw_results, config)
    
    # 2. Generate HTML and Save
    if final_report.top_news:
        html_content = generate_html(final_report)
        
        # Determine output dir: CLI > Config > Default "./docs"
        output_dir = args.output
        if not output_dir:
            output_dir = config.get("output", {}).get("directory", "./docs")
        
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        file_name = f"{topic.replace(' ', '_')}_{datetime.now().strftime('%Y-%m-%d')}.html"
        file_path = os.path.join(output_dir, file_name)
        
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            
            # Get absolute path and convert to file:// protocol
            abs_path = os.path.abspath(file_path)
            file_url = f"file://{abs_path}"
            
            logging.info(f"📄 HTML report saved to: {file_path}")
            
            # Output clickable link
            print("\n" + "="*50)
            print("🚀 Report Generation Complete!")
            print(f"🔗 Browser Link: {file_url}")
            # Try ANSI hyperlink
            print(f"👉 \033]8;;{file_url}\033\\Click here to open report in browser\033]8;;\033\\")
            print("="*50 + "\n")
            
        except Exception as e:
            logging.error(f"Failed to save HTML file: {e}")

if __name__ == "__main__":
    main()
