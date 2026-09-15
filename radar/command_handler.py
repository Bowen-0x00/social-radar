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
        if cmd.lower() in ("/status", "status", "状态"):
            return self._cmd_status()

        # 3. 立即触发一轮检索
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
🔹 **服务操作**:
- `/check` 或 `查动态`: 立即触发一次全源检索与 AI 评估
- `/status` 或 `状态`: 查看当前运行状态、免打扰与各参数

🔹 **免打扰休眠设置 (夜间不打扰)**:
- `/quiet 23:00-09:00`: 设置夜间休眠时段 (在此期间静默不推送)
- `/quiet off`: 关闭免打扰，恢复全天候推送

🔹 **回溯天数与频率调参**:
- `/days <天数>`: 设置抓取过去几天的动态 (如 `/days 3` 或 `/days 7`)
- `/interval <分钟>`: 设置轮询检查周期 (如 `/interval 30`)
- `/score <分数>`: 设置 AI 价值推送阈值 (默认 70 分)

🔹 **爬虫维护**:
- `/cookie <新Cookie>`: 微信直接热换知乎 Cookie，免登服务器！

💡 直接在微信对话框回复以上命令即可实时生效！"""

    def _cmd_status(self) -> str:
        cfg = self.service.cfg
        rc = cfg.get("radar", {})
        quiet_h = rc.get("quiet_hours", "23:00-09:00")
        quiet_desc = "休眠静默中 🌙" if is_in_quiet_hours(quiet_h) else "活跃监控中 🟢"

        return f"""📊 **SocialRadar 当前运行状态**
━━━━━━━━━━━━━━━━━━
🟢 **服务状态**: 守护监控中 (防反爬拟人抖动)
🌙 **免打扰时段**: `{quiet_h}` ({quiet_desc})
📅 **抓取回溯范围**: 最近 **{self.service.max_days_back}** 天内的动态/回答
⏰ **基础轮询周期**: 每 **{self.service.base_interval_minutes}** 分钟 (±{int(self.service.jitter_ratio*100)}% 随机抖动)
🎯 **AI 价值阈值**: {self.service.min_value_score} 分及以上推送
🤖 **大模型**: {cfg.get('llm', {}).get('model', 'gemini-3.8-flash')}
🔍 **监控源**: 知乎 (关注人动态 + 关注问题最新回答)"""

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
                return f"🎉 **知乎 Cookie 热更新成功！**\n\n- 账号: `{name}` (HTTP 200 OK)\n- 雷达监控已恢复正常采集。"
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
