# SocialRadar 社交雷达全套配置与防封实操作业程序 (SOP)

本文档记录了从零搭建 **SocialRadar** 所需的知乎凭证提取、防反爬封号安全策略、企业微信应用（1000004）配置以及云服务器 24/7 守护部署的完整作业程序。

---

## 目录
1. [知乎 Cookie 与个人凭证安全提取](#1-知乎-cookie-与个人凭证安全提取)
2. [防反爬虫与账号安全长效保护策略](#2-防反爬虫与账号安全长效保护策略)
   - [拟人化随机抖动调度 (Jitter)](#21-拟人化随机抖动调度-jitter)
   - [请求级微休眠与接口轮替](#22-请求级微休眠与接口轮替)
   - [限流自愈与指数退避](#23-限流自愈与指数退避)
3. [企业微信雷达专属应用配置 (Agent 1000004)](#3-企业微信雷达专属应用配置-agent-1000004)
4. [大模型价值评估画像定制与降噪规则](#4-大模型价值评估画像定制与降噪规则)
5. [Linux 云服务器 Systemd 守护进程与开机自启](#5-linux-云服务器-systemd-守护进程与开机自启)

---

## 1. 知乎 Cookie 与个人凭证安全提取

SocialRadar 通过模拟真实浏览器合法会话拉取动态，无需逆向高难度的签名加密，只需提取个人登录后的标准 Cookie：

### 1.1 提取步骤
1. 电脑端使用 Chrome / Edge 浏览器打开 [知乎首页](https://www.zhihu.com/) 并登录你的账号。
2. 按 `F12` 打开开发者工具，切换到 **网络 (Network)** 标签页。
3. 勾选 **Fetch/XHR** 过滤，刷新一次页面。
4. 在请求列表中随便点击一个发往 `zhihu.com` 的请求（如 `me` 或 `topstory`）。
5. 在右侧 **请求标头 (Request Headers)** 中找到 **`Cookie:`**：
   - 复制其全部内容（包含 `_xsrf`, `z_c0`, `d_c0` 等关键字段）。
6. 查看自己的个人主页 URL：
   `https://www.zhihu.com/people/{url_token}`
   记录下其中的 `{url_token}`（如 `Bowen`）。
7. 将两者填入 `config/config.yaml` 中：
   ```yaml
   zhihu:
     user_token: "你的url_token"
     cookie: "你的完整Cookie"
   ```

---

## 2. 防反爬虫与账号安全长效保护策略

由于知乎风控系统对自动化脚本极其敏感，本项目在底层架构上实现了多重深度防封保护：

### 2.1 拟人化随机抖动调度 (Jitter)
* **拒绝固定周期**：传统每 10 分钟整点运行极易被行为分析检测。
* **高斯/均匀抖动**：系统采用 `base_interval_minutes: 20` 搭配 `jitter_ratio: 0.3`。每次轮询后的休眠时间在 **14 分钟至 26 分钟** 之间完全随机波动，从统计学上完全打破周期性指纹。

### 2.2 请求级微休眠与接口轮替
* 在检查关注的每一个具体问题回答时，在各 HTTP 请求之间强制插入 **2.5 ~ 6.0 秒** 的随机拟人休眠（`_sleep_jitter()`）。
* 每次轮询仅拉取前 8~10 个最活跃问题，不做大面积并发扫库，确保请求量在正常真人浏览频率阈值以下。

### 2.3 限流自愈与指数退避
* 一旦服务端返回 HTTP 403 或 429（安全验证码拦截），系统自动捕获并在该轮直接挂起静默退避，绝不暴力重试，保障个人账号绝对安全。

---

## 3. 企业微信雷达专属应用配置 (Agent 1000004)

### 3.1 创建独立应用
1. 登录企业微信管理后台（work.weixin.qq.com）。
2. 进入 **应用管理** $\rightarrow$ 自建区点击 **“创建应用”**：
   - 名称填 `社交雷达` 或 `前沿动态`。
   - 上传雷达图标，可见范围选择自己。
   - 记录新应用的 `AgentId`（如 `1000004`）与 `Secret`。
3. 将凭据填入 `config/config.yaml`。

### 3.2 微信端呈现体验
* 采用时序双通道机制：
  1. 先向企业微信 App 推送完整的 Markdown 文章卡片（带超链接与详细见解）。
  2. 间隔 0.6 秒向个人手机微信推送 Textcard 原生卡片（直接在微信弹窗，支持点击【查看知乎回答】直达 App 内）。

---

## 4. 大模型价值评估画像定制与降噪规则

在 `config/user_profile.yaml` 中可以灵活配置你的技术偏好与严禁打扰的降噪规则：

* **高价值提分项**：
  在 `target_topics` 与 `keywords` 中声明你专注的研究领域（如计算机体系结构、存算一体、CXL、AI芯片、RISC-V等）。命中真实实测数据、架构权衡（Trade-off）的大模型会自动评予 **80~95 分的高分**。
* **低价值过滤项**：
  在 `exclude_patterns` 中声明娱乐八卦、纯情绪撕逼、无技术营养玩梗。大模型会自动评予 **0~20 分** 并标记 `is_noise: true`，绝不向手机弹窗骚扰。

---

## 5. Linux 云服务器 Systemd 守护进程与开机自启

在云服务器（如阿里云 Linux）后台保持 24 小时拟人轮询：

### 5.1 服务注册
服务模板已包含在 `deploy/social_radar.service`：
```bash
# 复制到系统服务目录并启动
cp deploy/social_radar.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now social_radar
```

### 5.2 运维命令
```bash
# 查看实时雷达监控与 AI 价值评分日志
journalctl -u social_radar -f

# 查看服务状态
systemctl status social_radar

# 重启雷达
systemctl restart social_radar
```

本地修改规则后，在 Windows 本地双击 `sync_to_aliyun.bat`，3 秒内即可无缝热重载生效。
