<div style="text-align:center">

<h1>AI Domain News Integrator</h1>

<b>English | <a href = "./README_CN.md">中文说明</a></b> <br>
<b>Version: v1.0.0</b>

</div>

**AI Domain News Integrator** is an intelligent information aggregation tool powered by LLMs. Instead of simple keyword searches, it constructs a **dynamic retrieval strategy** tailored to your specific domain or topic, delivering deep, structured insights.

It uses AI to **dynamically discover** high-quality vertical sources and integrates information from across the web to create professional daily briefings.

### ✨ Key Features

*   **🧠 AI-Driven Source Discovery**: Bye-bye static configs. The AI Planner automatically identifies relevant vertical domains (e.g., Hupu, GitHub, WSJ) and builds a tailored news network for your topic.
*   **🛡️ High Robustness**:
    *   **Multi-level Retry**: Handles network jitter and rate limits.
    *   **Compensation Mechanism**: Automatic "Gap Fill" ensures quota targets are met.
    *   **Stratified Sampling**: Balances core authoritative sources with broad discovery.
*   **⚡ High Concurrency**: Optimized multi-threaded engine for rapid, large-scale information gathering.
*   **📊 Smart Integration**: Combines multi-source aggregation, noise filtering, and deep summarization into a modern **HTML Report** via LLMs (e.g., Qwen-Max).


### 1. Prerequisites
Ensure you have **Python 3.10+**. Check with:
- **macOS / Linux**: `python3 --version`
- **Windows**: `python --version`

### 2. Installation (Step-by-Step)

**Step 1: Clone Repository**
```bash
git clone git@github.com:jgmiao/ai-news.git ai-news-integrator
cd ai-news-integrator
```

**Step 2: Create Virtual Environment (Recommended)**
```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows
python -m venv .venv
.venv\Scripts\activate
```

**Step 3: Install Dependencies**
```bash
pip install -r requirements.txt
```

## ⚙️ Configuration

### 1. Prepare LLM API
This project supports any OpenAI-compatible API.

**Parameters:**
*   `api_key`: Secret Key (Env Var: `API_KEY`).
*   `base_url`: API Endpoint (Env Var: `BASE_URL`).
*   `model_name`: Model ID (Env Var: `MODEL_NAME`).

**How to get API Key?**
*   **Qwen (Alibaba)**: Log in to [Aliyun Bailian Console](https://bailian.console.aliyun.com/) -> "API-KEY" -> "Create New Key".
*   **DeepSeek / OpenAI**: Visit their official consoles.

**Endpoint Reference**
*   **Qwen**: `https://dashscope.aliyuncs.com/compatible-mode/v1`
*   **DeepSeek**: `https://api.deepseek.com`
*   **OpenAI**: `https://api.openai.com/v1`

**Model Name**
*   **Qwen (Alibaba)**: `qwen-max` (Best), `qwen-plus`.
*   **DeepSeek**: `deepseek-chat`.
*   **OpenAI**: `gpt-4o`.
*   **Google Gemini**: `gemini-pro`.

### 2. Edit `config.yaml`

**Recommended Configuration (`config.yaml`):**

```yaml
llm:
  # Example for Qwen:
  api_key: "sk-xxxxxxxx" 
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model_name: "qwen-max" 
``` 

```yaml
search:
  # Total desired news items
  total_news: 50 
  min_per_core_source: 3
  
  # Network Proxy Configuration (Optional)
  # 1. External Access (Google/GitHub): Required. Set to your local proxy address.
  # 2. No Proxy / Domestic Use: Comment out or set to null.
  proxy:
    http: "http://127.0.0.1:7890"  
    https: "http://127.0.0.1:7890"

  news_sources:
    core:
      items:
        google_news: { match_names: ["google_news"] }
        github: { match_names: ["GitHub"], search_query: "site:github.com" }
        # ... (See default config.yaml for more)
```

## Usage

### Interactive Mode
Simply run the script, and it will prompt you for a topic.

```bash
./run.sh
# Input: "AI Agent"

```

### Command Line Argument
Pass the topic directly as an argument.

```bash
./run.sh "AI Agent"

```

### Non-interactive Automation
Set the `NEWS_TOPIC` environment variable.

```bash
export NEWS_TOPIC="Generative AI"
./run.sh

```

## Output

The script generates an HTML report in the `./docs` directory (or your configured output path).

**Example Output (`./docs/AI_Agent_2026-01-18.html`):**

The report features a modern HTML5 card layout with embedded CSS, offering a premium reading experience directly in your browser.



---

## License

[MIT](LICENSE)
