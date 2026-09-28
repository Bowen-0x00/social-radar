# SocialRadar - AI Social Dynamics & High-Value Content Radar

[English Documentation](README_EN.md) | [中文文档](README.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![LLM: AI_Evaluation](https://img.shields.io/badge/LLM-Value--Scoring-green.svg)](https://platform.openai.com/)

**SocialRadar** is a lightweight, private AI agent designed for researchers and software engineers.
It actively monitors **followed user dynamics and new answers to followed questions on Zhihu** (with modular architecture ready for X / Twitter integration). Powered by Large Language Models (LLMs), it **evaluates content quality, scores technical value (0-100), extracts core insights, and rigorously filters out gossip, internet drama, and low-effort memes**, pushing high-value cards directly to your **Personal WeChat** and Enterprise WeChat clients.

> 📖 **Full Setup & Anti-Ban SOP Guide**: See [Complete SOP Guide (docs/SOP_RADAR_SETUP.md)](docs/SOP_RADAR_SETUP.md) for step-by-step instructions on extracting Zhihu cookies, anti-scraping scheduling strategies, WeCom Agent 1000004 configuration, and systemd deployment.

---

## ✨ Key Features

- 🎯 **Dual-Track Zhihu Monitoring**:
  - **Followed People's Timeline**: Real-time tracking of new answers, upvotes, and technical articles by industry experts and academic mentors.
  - **Followed Question Updates**: Dedicated tracking of the latest answers to high-value technical questions (e.g., Near-Memory Computing, Future of Computer Architecture).
- 🛡️ **Industrial-Grade Anti-Scraping Protection**:
  - **Human-like Jitter Scheduling**: Replaces fixed polling cycles with a 20-minute base interval modulated by a ±30% random jitter (actual sleep fluctuates randomly between 14 and 26 minutes).
  - **Request-Level Micro-Delays**: Enforces a 2.5 to 6.0 second random pause between individual question lookups to stay strictly below rate-limiting thresholds.
  - **Self-Healing Rate Limit Protection**: Gracefully backs off upon encountering HTTP 403 or 429 status codes, avoiding repeated brute-force queries.
- 🧠 **LLM Content Quality Evaluation & Noise Filtering**:
  - Aligned with your technical and research interests (`config/user_profile.yaml`: Computer Architecture, PIM/PNM, CXL, AI Accelerators, RISC-V, Compilers, etc.).
  - Scores value (0-100) and distills **1~2 sentence core insights**, recommendation rationale, and tags.
  - **Aggressive Noise Suppression**: Emotional flame wars, celebrity gossip, and shallow jokes are automatically marked with low scores (<40) and `is_noise: true`, preventing phone notifications.
- 💬 **Sequential Dual-Channel WeChat Delivery**:
  - Pushes **Markdown rich-text** first (for optimal desktop layout in Enterprise WeChat).
  - Pushes native **Textcard cards** second (renders natively in Personal WeChat with clickable buttons to open the Zhihu answer).
- 🔌 **Extensible Platform Design**:
  - Built upon a modular `BaseMonitor` interface with an active stub for X (Twitter), ready for immediate activation once API credentials are provided.

---

## 🏗️ Architecture

```
       [ Zhihu (Cookie Session) ]        [ X / Twitter (Modular Stub) ]
                 │                                │
                 └────────────────┬───────────────┘
                                  ▼
                 ┌────────────────────────────────┐
                 │ 1. Anti-Scraping Data Capture  │
                 │    - 14~26 min Random Jitter   │
                 │    - 2.5~6s Request Delays     │
                 │    - SQLite Deduplication      │
                 └────────────────┬───────────────┘
                                  ▼
                 ┌────────────────────────────────┐
                 │ 2. LLM Value Evaluation Agent  │
                 │    - Research Profile Matching │
                 │    - Core Insights & Rationale │
                 │    - Noise & Fluff Filtering   │
                 └────────────────┬───────────────┘
                                  ▼
                 ┌────────────────────────────────┐
                 │ 3. Dual-Channel WeCom Delivery │
                 │    - Markdown Rich Text        │
                 │    - Native Personal Card      │
                 └────────────────────────────────┘
```


### 💬 Interactive WeChat Commands

| Command | Alias | Description | Example |
| :--- | :--- | :--- | :--- |
| **`/status`** | `状态` | **Live probe** of LLM connectivity & Zhihu Cookie health | `/status` |
| **`/llm model`** | `模型` | View active LLM model and recommended candidates | `/llm model` |
| **`/llm model <Name>`**| - | **Hot-switch active model** with pre-flight connection test | `/llm model gemini-3.1-pro-preview` |
| **`/llm <question>`** | - | Multi-turn conversational follow-up on latest post | `/llm How does this compare to CXL?` |
| **`/cookie <Cookie>`** | `更新知乎` | **Hot-update Zhihu cookie** directly from WeChat chat | `/cookie _xsrf=...` |
| **`/check`** | `查动态` | Trigger an immediate monitoring and evaluation round | `/check` |
| **`/quiet 23:00-09:00`**| `休眠` | Set quiet hours window (suppresses notifications) | `/quiet 23:00-09:00` |
| **`/days <N>`** | `范围` | Adjust lookback scope (default 7 days) | `/days 3` |
| **`/interval <min>`** | `频率` | Dynamically adjust base polling interval (default 20 min) | `/interval 30` |
| **`/score <N>`** | `阈值` | Adjust AI value threshold (default 70) | `/score 75` |
| **`/help`** | `帮助` | Display interactive command manual | `/help` |

---

## 🚀 Getting Started

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/Bowen-0x00/social-radar.git
cd social-radar

pip install -r requirements.txt
```

### 2. Configure Credentials
Copy the example configuration:
```bash
cp config/config.example.yaml config/config.yaml
```

Edit `config/config.yaml`:
1. **WeChat Configuration**: Fill in `corp_id`, `agent_id: 1000004`, and `corp_secret`.
2. **Zhihu Configuration**: Copy your full `cookie` and personal profile `user_token` from browser DevTools (Network tab).
3. **LLM Provider**: Fill in `base_url` and `api_key` (compatible with DeepSeek, Gemini, OpenAI, etc.).

### 3. Customize Your Research & Evaluation Profile
Edit `config/user_profile.yaml` to specify your focus areas and negative filters:
```yaml
target_topics:
  - "Computer Architecture and top-tier conferences (ISCA, MICRO, HPCA, ASPLOS)"
  - "Near-Memory Computing and Processing-in-Memory (PIM / PNM)"
  - "CXL Protocols, CXL.mem, Disaggregated Memory"
  - "AI Accelerator Chips and AI Compilers"
```

### 4. Run & Verify
```bash
# 1. Test WeChat push channel
python run.py --test-wechat

# 2. Test Zhihu data retrieval
python run.py --test-zhihu

# 3. Perform a single poll and exit
python run.py --once

# 4. Start continuous 24/7 background daemon
python run.py
```

---

## 📂 Project Structure

```
social_radar/
├── config/
│   ├── config.example.yaml      # Configuration template
│   └── user_profile.yaml        # Evaluation profile & noise patterns
├── radar/
│   ├── base_monitor.py          # Abstract base monitor interface
│   ├── zhihu_monitor.py         # Zhihu fetcher (timeline & questions)
│   ├── x_monitor.py             # X (Twitter) adapter stub
│   ├── llm_evaluator.py         # LLM evaluation & noise filtering agent
│   ├── notifier.py              # Sequential dual-channel WeChat notifier
│   ├── storage.py               # SQLite deduplication storage
│   ├── models.py                # Data models
│   └── service.py               # Main orchestration service
├── deploy/
│   └── social_radar.service     # Linux Systemd unit file
├── tests/
│   └── test_radar.py            # Test suite
├── run.py                       # CLI entrypoint
├── sync_to_aliyun.py            # Local to Aliyun sync script
├── sync_to_aliyun.bat           # Windows double-click batch script
├── requirements.txt             # Python dependencies
├── LICENSE                      # MIT License
└── README.md
```

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
