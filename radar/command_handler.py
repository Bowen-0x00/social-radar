"""微信交互指令处理器与动态配置热调中心 (SocialRadar)."""

import re
import yaml
import requests
from datetime import datetime, time
from typing import Dict, Any, Optional
from loguru import logger


def is_in_quiet_hours(quiet_str: str, now: Optional[datetime] = None) -> bool:
    """判定当前是否处于免打扰时段 (支持跨午夜，如 23:00-09:00)."""
    if not quiet_str or quiet_str.lower() in ("off", "none", "false", "0", "关闭"):
        return False
    try:
        parts = quiet_str.strip().split("-")
        if len(parts) != 2:
            return False
        sh, sm = map(int, parts[0].strip().split(":"))
        eh, em = map(int, parts[1].strip().split(":"))
        start_t = time(sh, sm)
        end_t = time(eh, em)
        cur_t = (now or datetime.now()).time()

        if start_t <= end_t:
            return start_t <= cur_t < end_t
        else:
            return cur_t >= start_t or cur_t < end_t
    except Exception:
        return False


class RadarCommandHandler:
    """处理用户在微信中输入的 SocialRadar 控制指令."""

    def __init__(self, service):
        self.service = service

    def handle_command(self, text: str, from_user: str = "@all") -> str:
        cmd = text.strip()
        logger.info(f"[Command] 收到 SocialRadar 指令: {cmd}")

        # 1. 帮助
        if cmd.lower() in ("/help", "help", "帮助", "?", "？"):
            return self._cmd_help()

        # 2. 状态看板 (免打扰、回溯天数、轮询频率三元组)
        if cmd.lower() in ("/status", "status", "状态", "/s"):
            return self._cmd_status()
        # 3. 立即触发一轮检索
        # 2.5 AI 深度追问: /llm <问题> 或 /llm last <问题> 或 /llm history
        if cmd.lower().startswith(("/llm", "／llm")):
            llm_text = cmd[4:].strip() if len(cmd) > 4 else ""
            return self._cmd_chat_llm(llm_text, from_user)

        if cmd.lower() in ("/check", "check", "/run", "run", "查动态", "立即检查"):
            return self._cmd_check()

        # 4. 免打扰休眠设置: /quiet 23:00-09:00 或 /quiet off 或 休眠 23:00-09:00
        m_quiet = re.match(r'^(?:/quiet|quiet|/sleep|sleep|休眠)\s*(.+)$', cmd, re.IGNORECASE)
        if m_quiet:
            val = m_quiet.group(1).strip()
            return self._cmd_set_quiet_hours(val)

        # 5. 回溯天数设置: /days 3 或 范围 3
        m_days = re.match(r'^(?:/days|days|范围)\s*(\d+)$', cmd, re.IGNORECASE)
        if m_days:
            days = int(m_days.group(1))
            return self._cmd_set_days(days)

        # 6. 轮询周期设置: /interval 30 或 频率 30 (分钟)
        m_interval = re.match(r'^(?:/interval|interval|频率)\s*(\d+)$', cmd, re.IGNORECASE)
        if m_interval:
            mins = int(m_interval.group(1))
            return self._cmd_set_interval(mins)

        # 7. 价值门槛分数: /score 75 或 阈值 75
        m_score = re.match(r'^(?:/score|score|阈值)\s*(\d+)$', cmd, re.IGNORECASE)
        if m_score:
            score = int(m_score.group(1))
            return self._cmd_set_score(score)

        # 8. 知乎 Cookie 热更新: /cookie <新Cookie>
        m_cookie = re.match(r'^(?:/cookie|cookie|更新知乎)\s*(.+)$', cmd, re.IGNORECASE | re.DOTALL)
        if m_cookie:
            return self._cmd_update_cookie(m_cookie.group(1).strip())

        return (
            f"❓ 未识别的指令: `{cmd}`\n\n"
            f"发送 `/help` 查看支持的调参指令，如 `/quiet 23:00-09:00`、`/days 3`、`/interval 30`。"
        )

    def _cmd_help(self) -> str:
        return """📖 **SocialRadar 社交雷达控制手册**
━━━━━━━━━━━━━━━━━━
🔹 **AI 深度追问与多轮对话**:
• `/llm <问题>`: 对雷达最新推送的动态/文章展开深度提问
• `/llm last <问题>`: 追问最新一条动态
• `/llm <ID> <问题>`: 追问指定 ID 内容 (如 `/llm 12 ...`)
• `/llm history`: 查看最新动态的概况与已有追问历史
• `/llm model`: 查看大模型连接状态与推荐模型列表
• `/llm model <模型名称>`: 切换当前大模型 (如 `/llm model gemini-3.1-pro-preview`)
🔹 **服务操作**:
• `/check` 或 `查动态`: 立即触发一次全源检索与 AI 评估
• `/status` 或 `状态`: 查看当前运行状态、免打扰与各参数

🔹 **免打扰休眠设置 (夜间不打扰)**:
• `/quiet 23:00-09:00`: 设置夜间休眠时段 (在此期间静默不推送)
• `/quiet off`: 关闭免打扰，恢复全天候推送

🔹 **回溯天数与频率调参**:
• `/days <天数>`: 设置抓取过去几天的动态 (如 `/days 3` 或 `/days 7`)
• `/interval <分钟>`: 设置轮询检查周期 (如 `/interval 30`)
• `/score <分数>`: 设置 AI 价值推送阈值 (默认 70 分)

🔹 **爬虫维护**:
• `/cookie <新Cookie>`: 微信直接热换知乎 Cookie，免登服务器！"""

    def _cmd_status(self) -> str:
        cfg = self.service.cfg
        rc = cfg.get("radar", {})
        quiet_h = rc.get("quiet_hours", "23:00-09:00")
        quiet_desc = "休眠静默中 🌙" if is_in_quiet_hours(quiet_h) else "活跃监控中 🟢"

        # 1. 实时探测大模型健康状态
        llm_model = self.service.evaluator.model
        llm_ok, llm_cost = self.service.evaluator.test_model(llm_model)
        llm_badge = f"🟢 连通正常 (耗时: {llm_cost})" if llm_ok else f"🔴 异常 ({llm_cost})"

        # 2. 实时探测知乎 Cookie 状态
        zc = cfg.get("zhihu", {})
        cookie = zc.get("cookie", "")
        cookie_desc = "⚪ 未配置"
        if cookie:
            try:
                headers = {
                    "accept": "*/*",
                    "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "cookie": cookie
                }
                r = requests.get("https://www.zhihu.com/api/v4/me?include=is_realname", headers=headers, timeout=5)
                if r.status_code == 200:
                    u_name = r.json().get("name", "")
                    cookie_desc = f"🟢 正常生效 (账号: {u_name or '已登录'})"
                else:
                    cookie_desc = f"🔴 凭据失效 (HTTP {r.status_code})"
            except Exception as e:
                cookie_desc = f"⚠️ 探测超时 ({str(e)[:30]})"

        return f"""📊 **SocialRadar 当前运行状态看板**
━━━━━━━━━━━━━━━━━━
🟢 **服务状态**: 守护监控中 (防反爬拟人抖动)
🤖 **大模型引擎**: `{llm_model}` -> {llm_badge}
🍪 **知乎抓取凭据**: {cookie_desc}
🌙 **免打扰时段**: `{quiet_h}` ({quiet_desc})
📅 **抓取回溯范围**: 最近 **{self.service.max_days_back}** 天内的动态/回答
⏰ **基础轮询周期**: 每 **{self.service.base_interval_minutes}** 分钟 (±{int(self.service.jitter_ratio*100)}% 随机抖动)
🎯 **AI 价值阈值**: {self.service.min_value_score} 分及以上推送
🔍 **监控源**: 知乎 (关注人动态 + 关注问题最新回答)

💡 提示:
• 发送 `/llm model` 可切换/测试其他模型
• 发送 `/cookie <新Cookie>` 可热更知乎凭据"""
    def _cmd_chat_llm(self, llm_text: str, from_user: str) -> str:
        """处理针对社交雷达文章的 /llm 追问."""
        parts = llm_text.split(maxsplit=1)
        if not parts:
            return (
                "💡 **SocialRadar AI 深度追问指南**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "• `/llm <问题>`: 对雷达最新捕获并推送的动态/文章展开深度提问\n"
                "• `/llm last <问题>`: 追问最新一条动态\n"
                "• `/llm <ID> <问题>`: 追问指定动态\n"
                "• `/llm history`: 查看最新动态的概况与已有追问历史"
            )

        first_token = parts[0].strip().lower()
        if first_token in ("model", "models", "模型"):
            model_arg = parts[1].strip() if len(parts) > 1 else ""
            return self._cmd_llm_model(model_arg)

        if first_token in ("last", "latest") or (first_token.isalnum() and len(first_token) >= 8 and not any('\u4e00' <= c <= '\u9fff' for c in first_token)) or first_token.isdigit():
            target = first_token
            question = parts[1].strip() if len(parts) > 1 else ""
        else:
            target = "last"
            question = llm_text

        # 查找条目
        with self.service.storage._get_connection() as conn:
            row = None
            if target in ("last", "latest"):
                cur = conn.execute("SELECT * FROM processed_items WHERE is_notified = 1 ORDER BY created_at DESC LIMIT 1")
                row = cur.fetchone()
                if not row:
                    cur = conn.execute("SELECT * FROM processed_items ORDER BY created_at DESC LIMIT 1")
                    row = cur.fetchone()
            else:
                cur = conn.execute("SELECT * FROM processed_items WHERE item_id = ? OR title LIKE ? ORDER BY created_at DESC LIMIT 1", (target, f"%{target}%"))
                row = cur.fetchone()

        if not row:
            return f"❌ 未在雷达库中找到相关动态 (查询目标: `{target}`)。\n请确认是否有已推送的动态，或发送 `/check` 立即检索一次！"

        item = dict(row)
        item_id = item["item_id"]
        title = item.get("title", "无标题动态")
        author = item.get("author", "未知作者")
        score = item.get("value_score", 0)
        core_insight = item.get("core_insight", "")

        # 查看概况
        if not question or question.lower() == "history":
            hist = self.service.storage.get_chat_history(item_id) if hasattr(self.service.storage, "get_chat_history") else []
            return (
                f"📡 **当前选中雷达动态**\n"
                f"📌 《{title}》\n"
                f"👤 作者: {author} | 🔥 价值评分: {score}分\n"
                f"💡 核心洞察: {core_insight}\n\n"
                f"💬 已有追问历史: {len(hist)} 条消息。\n"
                f"您可以发送：`/llm 您的追问问题` 与 AI 继续探讨！"
            )

        # 调用大模型执行对话
        hist = self.service.storage.get_chat_history(item_id) if hasattr(self.service.storage, "get_chat_history") else []
        context_parts = [
            f"【动态/文章标题】: {title}",
            f"【作者】: {author}",
            f"【来源平台】: {item.get('platform', '')}",
            f"【原文链接】: {item.get('url', '')}",
            f"【AI价值评分】: {score}分",
            f"【前期核心洞察与分析】:\n{core_insight}"
        ]
        doc_context = "\n".join(context_parts)
        system_prompt = f"""你是一位敏锐的社交舆情与前沿技术观察助手。
请基于以下由【SocialRadar】监控并分析的内容，回答用户的追问。

--- 内容与洞察上下文 ---
{doc_context}
--- 结束 ---

回答要求：
1. 严格依据上述内容与洞察作答，深入剖析舆论热点或技术观点。
2. 语言条理清晰，层次分明，逻辑严密，适合企业微信或手机端阅读。
3. 控制在 500 字以内，避免冗长废话，突出要点。"""

        messages = [{"role": "system", "content": system_prompt}]
        for h in hist[-6:]:
            r = h.get("role", "user")
            c = h.get("content", "")
            if r in ("user", "assistant") and c:
                messages.append({"role": r, "content": c})
        messages.append({"role": "user", "content": question})

        client = self.service.evaluator.client
        model = self.service.evaluator.model
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                max_tokens=800
            )
            ans = resp.choices[0].message.content.strip()
            if hasattr(self.service.storage, "add_chat_message"):
                self.service.storage.add_chat_message(item_id, from_user, "user", question)
                self.service.storage.add_chat_message(item_id, from_user, "assistant", ans)
            return (
                f"🤖 **【SocialRadar·深度探讨】**\n"
                f"📄 《{title}》\n"
                f"❓ 问: {question}\n\n"
                f"💡 答:\n{ans}"
            )
        except Exception as e:
            return f"⚠️ 追问回答生成失败: {e}"
    def _cmd_check(self) -> str:
        import threading
        threading.Thread(target=self.service.poll_all_monitors, daemon=True).start()
        return "🔍 **已立即触发动态检索**\n\n正在后台拉取知乎最新动态与关注问题回答，大模型评估达标后将为您推送卡片！"

    def _cmd_set_quiet_hours(self, val: str) -> str:
        clean_val = val.strip()
        if clean_val.lower() in ("off", "none", "false", "0", "关闭"):
            self.service.quiet_hours = "off"
            self._update_yaml(["radar", "quiet_hours"], "off")
            return "✅ **免打扰休眠已关闭**\n\n系统将恢复全天候 24 小时即时推送。"

        if not re.match(r'^\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}$', clean_val):
            return "⚠️ 格式不正确！请使用 `HH:MM-HH:MM` 格式，如 `/quiet 23:00-09:00`，或发送 `/quiet off` 关闭。"

        clean_val = re.sub(r'\s+', '', clean_val)
        self.service.quiet_hours = clean_val
        self._update_yaml(["radar", "quiet_hours"], clean_val)
        return f"🌙 **夜间免打扰休眠时段已生效！**\n\n时段: **{clean_val}**\n在该时段内系统静默记录，绝不打扰您的休息。"

    def _cmd_set_days(self, days: int) -> str:
        if days <= 0:
            return "⚠️ 抓取天数必须大于 0 天。"
        self.service.max_days_back = days
        self._update_yaml(["radar", "max_days_back"], days)
        return f"✅ **抓取回溯范围已修改**\n\n新范围: 最近 **{days}** 天内的动态与回答 (已持久化保存)。"

    def _cmd_set_interval(self, mins: int) -> str:
        if mins < 5:
            return "⚠️ 轮询周期不能小于 5 分钟，以防触发知乎风控限制。"
        self.service.base_interval_minutes = mins
        self._update_yaml(["radar", "base_interval_minutes"], mins)
        return f"✅ **轮询基础周期已修改**\n\n新周期: 每 **{mins}** 分钟检查一次 (±{int(self.service.jitter_ratio*100)}% 随机抖动，已持久化保存)。"

    def _cmd_set_score(self, score: int) -> str:
        if not (0 <= score <= 100):
            return "⚠️ 分数必须在 0 到 100 之间。"
        self.service.min_value_score = score
        self.service.evaluator.min_value_score = score
        self._update_yaml(["radar", "min_value_score"], score)
        return f"✅ **AI 价值推送阈值已修改**\n\n新阈值: **{score}** 分 (已持久化保存)。"
    def _cmd_llm_model(self, model_arg: str) -> str:
        """处理 /llm model 查看状态或切换大模型指令."""
        # 1. 查询当前模型与状态
        if not model_arg or model_arg.lower() in ("status", "check", "list", "状态"):
            ok, cost_or_err = self.service.evaluator.test_model(self.service.evaluator.model)
            status_badge = f"🟢 连通正常 (响应耗时: {cost_or_err})" if ok else f"🔴 异常 ({cost_or_err})"

            return (
                "🤖 **SocialRadar 大模型状态看板**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"📌 当前主模型: `{self.service.evaluator.model}`\n"
                f"⚡ 实时连通性: {status_badge}\n"
                f"🌐 接口地址: `{self.service.evaluator.base_url}`\n\n"
                "📋 **常用候选模型**:\n"
                "• `gemini-3.1-pro-preview` (推荐：稳定、速度快)\n"
                "• `gemini-3.6-flash`\n"
                "• `gemini-3.8-flash`\n"
                "• `deepseek-chat`\n\n"
                "💡 **切换模型命令**:\n"
                "发送：`/llm model <模型名称>`\n"
                "例如：`/llm model gemini-3.1-pro-preview`"
            )

        # 2. 切换模型
        target_model = model_arg.strip()
        logger.info(f"[SocialRadar] 用户请求切换大模型至: {target_model}")

        ok, cost_or_err = self.service.evaluator.test_model(target_model)
        if ok:
            old_model = self.service.evaluator.model
            self.service.evaluator.model = target_model
            self._update_yaml(["llm", "model"], target_model)
            return (
                "✅ **大模型切换成功！**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"🔄 原模型: `{old_model}`\n"
                f"🤖 新模型: `{target_model}`\n"
                f"⚡ 连通性测试: 🟢 通过 (耗时: {cost_or_err})\n"
                "💾 配置文件已持久化保存，后续雷达动态评估将自动使用该模型！"
            )
        else:
            return (
                "⚠️ **模型连通性测试失败！**\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"目标模型: `{target_model}`\n"
                f"❌ 失败原因: {cost_or_err}\n\n"
                f"🛡️ 为保障监控不中断，雷达仍保持当前可用模型: `{self.service.evaluator.model}`\n"
                "💡 建议：发送 `/llm model` 查看可用候选模型列表。"
            )


    def _cmd_update_cookie(self, new_cookie: str) -> str:
        if len(new_cookie) < 30 or "z_c0" not in new_cookie:
            return "⚠️ Cookie 格式似乎不完整，请完整复制网络请求中的 Cookie 标头。"

        self._update_yaml(["zhihu", "cookie"], new_cookie)
        # 热更内存中的 session header
        for m in self.service.monitors:
            if m.get_platform_name() == "zhihu":
                m.session.headers["cookie"] = new_cookie

        # 探测有效性
        test_url = "https://www.zhihu.com/api/v4/me?include=is_realname"
        headers = {
            "accept": "*/*",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "cookie": new_cookie
        }
        try:
            r = requests.get(test_url, headers=headers, timeout=10)
            if r.status_code == 200:
                name = r.json().get("name", "用户")
                # 跨项目同步更新 wechat_obsidian 的 config.yaml
                for obs_path in ["../wechat_obsidian/config.yaml", "/root/wechat_obsidian/config.yaml"]:
                    if os.path.exists(obs_path):
                        try:
                            with open(obs_path, "r", encoding="utf-8") as f:
                                o_cfg = yaml.safe_load(f) or {}
                            o_cfg.setdefault("zhihu", {})["cookie"] = new_cookie
                            with open(obs_path, "w", encoding="utf-8") as f:
                                yaml.dump(o_cfg, f, allow_unicode=True, sort_keys=False)
                            logger.info(f"[SocialRadar] 同步热更新 {obs_path} 知乎 Cookie 成功！")
                        except Exception as e:
                            logger.warning(f"[SocialRadar] 同步更新 {obs_path} 异常: {e}")
                return f"🎉 **知乎 Cookie 热更新成功！**\n\n- 账号: `{name}` (HTTP 200 OK)\n- 雷达与 Obsidian 助手均已同步更新凭据。"
            return f"⚠️ Cookie 已写入，但知乎服务端验证返回 HTTP {r.status_code}，可能触发了滑块验证码。"
        except Exception as e:
            return f"⚠️ Cookie 已保存，但验证异常: {e}"

    def _update_yaml(self, keys: list, value: Any):
        p = "config/config.yaml"
        import os
        if not os.path.exists(p):
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            cur = data
            for k in keys[:-1]:
                cur = cur.setdefault(k, {})
            cur[keys[-1]] = value
            with open(p, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            logger.error(f"[Command] 持久化配置异常: {e}")
