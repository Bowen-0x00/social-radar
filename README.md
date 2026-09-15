# SocialRadar - 社交前沿动态与高价值内容监控雷达

[中文文档](README.md) | [English Documentation](README_EN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![LLM: AI_Evaluation](https://img.shields.io/badge/LLM-Value--Scoring-green.svg)](https://platform.openai.com/)

**SocialRadar** 是一个轻量级、面向科研学者与工程师的私有化社交前沿雷达 Agent。
能够持续监听**知乎关注人的动态**与**关注问题的最新回答**（预留 X/Twitter 平台适配框架），借助大语言模型（LLM）实现**高质量技术内容深度甄别、智能打分与核心见解提炼**，严格过滤口水八卦水帖，并通过企业微信与个人微信双通道实时推送高价值干货卡片。

> 📖 **全套配置与防封避坑手册**：详见 [社交雷达全套 SOP 指南 (docs/SOP_RADAR_SETUP.md)](docs/SOP_RADAR_SETUP.md)，涵盖知乎 Cookie 提取、防反爬封号长周期策略、企业微信 1000004 应用配置与云服务器守护进程。

---

## ✨ 核心特性

- 🎯 **知乎双轨动态监控**：
  - **关注人的动态**：实时追踪业内技术大牛、学术导师的最新回答、赞同与专栏发文。
  - **关注问题的最新回答**：定向追踪高价值专业问题（如《存算一体前景》、《体系结构未来》）下的最新答复。
- 🛡️ **工业级防反爬虫长效保护策略**：
  - **拟人化随机 Jitter 调度**：告别定时整点爬取，基础周期 20 分钟搭配 ±30% 动态随机浮动（实际每次休眠在 14~26 分钟之间波动）。
  - **请求级微休眠**：在拉取不同问题回答时强制插入 2.5 ~ 6.0 秒的随机休眠，严格控制请求频次在真人日常浏览量级以下。
  - **限流自愈保护**：捕获 403 / 429 频控异常即刻静默退避，绝不强行重试，保障账号绝对安全。
- 🧠 **大模型深度价值甄别与自动降噪**：
  - 对齐个人学术与技术画像（`config/user_profile.yaml`，如体系结构、存算一体、CXL、AI加速器、RISC-V、编译器等）。
  - 自动打出 0~100 价值评分，提炼 **1~2 句核心创新/观点见解**、推荐理由与标签。
  - **硬核降噪**：对纯情绪撕逼、娱乐同人八卦、浅层玩梗段子自动判定为低分（<40分）并标记 `is_noise: true`，绝不向手机弹窗打扰。
- 💬 **微信时序双通道推送**：
  - 先推企业微信 Markdown 富文本（桌面客户端享受清晰排版与原文字样）。
  - 后推个人手机微信 Textcard 原生卡片（直接在个人微信弹窗，支持点击【查看知乎回答】直达 App 查阅）。
- 🔌 **平台可扩展设计**：
  - 采用模块化 `BaseMonitor` 抽象架构，预留 X (Twitter) 平台适配器插槽，账号就绪后填入 Bearer Token 即可无缝激活。

---

## 🏗️ 系统架构图

```
      [ 知乎 (Cookie 授权) ]         [ X / Twitter (预留插槽) ]
                 │                                │
                 └────────────────┬───────────────┘
                                  ▼
                 ┌────────────────────────────────┐
                 │ 1. 防反爬拟人化调度与数据采集  │
                 │    - 14~26分钟动态随机 Jitter  │
                 │    - 请求间 2.5~6秒微休眠      │
                 │    - SQLite 幂等去重           │
                 └────────────────┬───────────────┘
                                  ▼
                 ┌────────────────────────────────┐
                 │ 2. LLM 内容价值深度评估 Agent  │
                 │    - 计算机体系结构与AI芯片画像│
                 │    - 提炼核心见解与推荐理由    │
                 │    - 严格过滤口水八卦与水帖    │
                 └────────────────┬───────────────┘
                                  ▼
                 ┌────────────────────────────────┐
                 │ 3. 微信时序双通道推送分发      │
                 │    - 企微 Markdown 富文本      │
                 │    - 个人微信 Textcard 原生卡片│
                 └────────────────────────────────┘
```

---

## 🚀 快速上手指南

### 1. 克隆代码与安装依赖
```bash
git clone https://github.com/Bowen-0x00/social-radar.git
cd social-radar

# 安装依赖
pip install -r requirements.txt
```

### 2. 准备配置文件
复制配置模板：
```bash
cp config/config.example.yaml config/config.yaml
```

编辑 `config/config.yaml` 填入您的凭据：
1. **企业微信通知配置**：填入 `corp_id`、`agent_id: 1000004` 与 `corp_secret`。
2. **知乎配置**：在浏览器 F12 网络抓包中复制您的完整 `cookie` 与个人主页 `user_token`。
3. **大模型配置**：支持 DeepSeek、Gemini、OpenAI 等兼容接口，填入 `base_url` 与 `api_key`。

### 3. 定制您的价值关注画像
编辑 `config/user_profile.yaml`，按需增删您关注的技术方向与严禁打扰的关键词：
```yaml
target_topics:
  - "计算机体系结构 (Computer Architecture) 与四大顶会 (ISCA, MICRO, HPCA, ASPLOS)"
  - "近存计算、存算一体 (PIM / PNM) 的前景、落地瓶颈与真实工业实践"
  - "CXL 协议、CXL.mem、解耦内存架构"
  - "AI 加速器芯片架构与 AI 编译器"
```

### 4. 运行与验证
```bash
# 1. 测试企业微信 1000004 通知通道
python run.py --test-wechat

# 2. 测试知乎数据抓取与防爬机制
python run.py --test-zhihu

# 3. 单次执行全量抓取与大模型评估后退出
python run.py --once

# 4. 启动 24 小时后台常驻守护监控 (拟人随机周期)
python run.py
```

---

## 📂 项目结构

```
social_radar/
├── config/
│   ├── config.example.yaml      # 配置模板 (微信凭据、知乎Cookie、LLM参数)
│   └── user_profile.yaml        # 用户技术偏好与降噪过滤画像
├── radar/
│   ├── base_monitor.py          # 跨平台监控器基类接口
│   ├── zhihu_monitor.py         # 知乎监控器 (关注人动态 + 关注问题回答)
│   ├── x_monitor.py             # X (Twitter) 监控器框架插槽 (预留)
│   ├── llm_evaluator.py         # 大模型内容价值甄别与自动打标 Agent
│   ├── notifier.py              # 微信时序双通道推送器
│   ├── storage.py               # SQLite 历史动态记忆与去重
│   ├── models.py                # 统一数据结构定义
│   └── service.py               # 核心编排业务主服务
├── deploy/
│   └── social_radar.service     # Linux Systemd 守护服务单元
├── tests/
│   └── test_radar.py            # 自动化测试套件
├── run.py                       # CLI 命令行入口
├── sync_to_aliyun.py            # 本地代码一键同步阿里云工具
├── sync_to_aliyun.bat           # Windows 双击一键同步批处理
├── requirements.txt             # 依赖清单
├── LICENSE                      # MIT 开源许可证
└── README.md
```

---

## 📄 开源许可证

本项目采用 [MIT License](LICENSE) 许可证。
