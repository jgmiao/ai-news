#!/bin/bash
# Activate virtual environment and run the app
source .venv/bin/activate
# Run as module
python3 -m ai_news.main "$@"
