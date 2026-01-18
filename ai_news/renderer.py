import os
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from ai_news.models import NewsReport

def generate_html(report: NewsReport) -> str:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d %A")
    today_ymd = now.strftime("%Y-%m-%d")
    
    # Group news
    today_news = []
    earlier_news = []
    
    # Safe date sorting/grouping
    def parse_date(d):
        try:
            return datetime.strptime(d, "%Y-%m-%d")
        except:
            return datetime.min

    # Sort descending
    sorted_news = sorted(report.top_news, key=lambda x: parse_date(x.date), reverse=True)

    for news in sorted_news:
        if news.date == today_ymd:
            today_news.append(news)
        else:
            earlier_news.append(news)
    
    # Setup Jinja2 Environment
    # Assuming templates is in ai_news/templates/ relative to this file?
    # Or relative to package root.
    # We will assume: current file is at ai_news/renderer.py
    # Templates are at ai_news/templates/
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    templates_dir = os.path.join(current_dir, "templates")
    
    env = Environment(loader=FileSystemLoader(templates_dir))
    template = env.get_template("report.html")
    
    html = template.render(
        topic=report.topic,
        date_str=date_str,
        prologue=report.prologue,
        today_news=today_news,
        earlier_news=earlier_news
    )
    
    return html
