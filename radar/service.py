"""SocialRadar 核心业务编排主服务."""

import os
import time
import random
import yaml
from typing import List, Dict, Any, Optional
from loguru import logger

from .models import SocialItem, EvaluationResult
from .storage import RadarStorage
from .notifier import WeChatNotifier
from .llm_evaluator import LLMEvaluator
from .zhihu_monitor import ZhihuMonitor
from .x_monitor import XMonitor
from .command_handler import RadarCommandHandler, is_in_quiet_hours


class SocialRadarService:
    """社交前沿雷达业务控制器."""

    def __init__(self, config_path: str = "config/config.yaml"):
        if not os.path.exists(config_path):
            if os.path.exists("config/config.example.yaml"):
                config_path = "config/config.example.yaml"
            else:
                raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, "r", encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)

        # 1. 初始化存储
        rc = self.cfg.get("radar", {})
        self.storage = RadarStorage(db_path=rc.get("db_path", "data/social_radar.db"))
        self.min_value_score = int(rc.get("min_value_score", 70))
        self.base_interval_minutes = int(rc.get("base_interval_minutes", 20))
        self.jitter_ratio = float(rc.get("jitter_ratio", 0.3))
        self.quiet_hours = str(rc.get("quiet_hours", "23:00-09:00"))
        self.max_days_back = int(rc.get("max_days_back", 7))
        # 2. 初始化微信通知 (1000004)
        wc = self.cfg.get("wechat", {})
        self.notifier = WeChatNotifier(
            corp_id=wc.get("corp_id", ""),
            agent_id=int(wc.get("agent_id", 1000004)),
            corp_secret=wc.get("corp_secret", ""),
            default_to_user=wc.get("to_user", "@all")
        )

        # 3. 初始化 LLM 价值评估引擎
        lc = self.cfg.get("llm", {})
        self.evaluator = LLMEvaluator(
            base_url=lc.get("base_url", ""),
            api_key=lc.get("api_key", ""),
            model=lc.get("model", "gemini-3.8-flash"),
            temperature=float(lc.get("temperature", 0.2)),
            proxy=lc.get("proxy"),
            profile_path="config/user_profile.yaml",
            min_value_score=self.min_value_score,
            enable=bool(lc.get("enable", True))
        )

        # 4. 初始化各平台监控器
        self.monitors = []
        zc = self.cfg.get("zhihu", {})
        if zc.get("enabled", True):
            self.monitors.append(ZhihuMonitor(
                cookie=zc.get("cookie", ""),
                user_token=zc.get("user_token", "Bowen"),
                check_moments=bool(zc.get("check_moments", True)),
                check_questions=bool(zc.get("check_questions", True)),
                max_questions_per_round=int(zc.get("max_questions_per_round", 8)),
                delay_range=tuple(zc.get("request_delay_range", [2.5, 6.0])),
                notifier=self.notifier
            ))

        xc = self.cfg.get("x_twitter", {})
        self.monitors.append(XMonitor(
            enabled=bool(xc.get("enabled", False)),
            bearer_token=xc.get("bearer_token", ""),
            monitored_users=xc.get("monitored_users", [])
        ))

        # 5. 命令交互与监听服务
        self.cmd_handler = RadarCommandHandler(self)
        self._start_command_server(port=8085)
    def send_startup_message(self):
        """发送服务启动与监听范围通知到微信."""
        platforms = [m.get_platform_name() for m in self.monitors]
        title = "📡 SocialRadar 社交动态雷达已就绪"
        summary = f"状态: 🟢 运行中 | 监控平台: {', '.join(platforms)}"

        details = f"<b>监控重点</b>: 关注人动态 + 关注问题最新回答<br/>" \
                  f"<b>抓取范围</b>: 最近 {self.max_days_back} 天<br/>" \
                  f"<b>免打扰时段</b>: {self.quiet_hours} (夜间静默不打扰)<br/>" \
                  f"<b>基础周期</b>: 每 {self.base_interval_minutes} 分钟 (随机抖动 ±{int(self.jitter_ratio*100)}%)<br/>" \
                  f"<b>推送阈值</b>: ≥ {self.min_value_score} 分 (大模型自动降噪)<br/>" \
                  f"<div class=\"highlight\">💡 <b>微信快捷指令支持</b>:<br/>" \
                  f"• <code>/check</code> : 立即触发全源检索<br/>" \
                  f"• <code>/status</code> : 查看当前状态看板<br/>" \
                  f"• <code>/quiet 23:00-09:00</code> : 设置夜间免打扰<br/>" \
                  f"• <code>/days 3</code> : 修改回溯抓取天数<br/>" \
                  f"• <code>/interval 30</code> : 修改轮询周期(分钟)<br/>" \
                  f"• <code>/score 75</code> : 修改价值推送阈值<br/>" \
                  f"• <code>/cookie &lt;新Cookie&gt;</code> : 微信热换知乎凭据<br/>" \
                  f"• <code>/help</code> : 查看完整指令手册</div>"

        md_content = f"""### 📡 SocialRadar 社交雷达服务已就绪！
**状态**: 🟢 正常运行中 (防反爬拟人抖动)
**监控平台**: {', '.join(platforms)}
**抓取范围**: 最近 **{self.max_days_back}** 天内的动态/回答
**免打扰时段**: `{self.quiet_hours}` (夜间静默不推送)
**轮询策略**: 基础周期 {self.base_interval_minutes} 分钟 (±{int(self.jitter_ratio*100)}% 随机抖动)
**价值阈值**: 🔥 **{self.min_value_score} 分** 及以上推送
**大模型**: {self.cfg['llm']['model']}

> 💡 **微信快捷指令支持**：在此对话框回复以下命令可实时调参：
> - `/check` 或 `查动态`：立即触发一次全源检索
> - `/status` 或 `状态`：查看当前配置看板
> - `/quiet 23:00-09:00`：设置夜间免打扰休眠时段
> - `/quiet off`：关闭免打扰时段
> - `/days <天数>`：动态调整回溯天数 (如 `/days 3`)
> - `/interval <分钟>`：动态调整轮询周期 (如 `/interval 30`)
> - `/score <分数>`：动态调整价值推送阈值 (如 `/score 75`)
> - `/cookie <新Cookie>`：免登录服务器直接热更知乎 Cookie！
> - `/help`：获取完整指令手册"""

        self.notifier.send_dual_notification(
            title=title,
            summary=summary,
            details=details,
            markdown_content=md_content,
            url="https://www.zhihu.com/follow",
            btntxt="进入知乎"
        )

    def process_item(self, item: SocialItem):
        """处理单条动态或问答：去重、AI 评估、价值决策与通知."""
        if self.storage.is_processed(item.item_id):
            logger.debug(f"[{item.platform}] 条目已处理过，跳过: {item.item_id}")
            return

        logger.info(f"[{item.platform}] 开始 AI 评估: [{item.action}] {item.title[:35]} (作者: {item.author})")

        # LLM 价值深度评估
        res: EvaluationResult = self.evaluator.evaluate(item)
        logger.info(f"[{item.platform}] 评估结果: 价值得分={res.value_score} (阈值: {self.min_value_score}), 噪音={res.is_noise}, 需推送={res.need_notify}")
        # 检查是否发生大模型评估异常并告警
        if getattr(self.evaluator, "last_error", None):
            self.notifier.send_alert(
                alert_key="social_radar_llm_alert",
                title="⚠️ 【社交雷达 - 大模型评估告警】",
                content=(
                    f"🤖 当前主模型: `{self.evaluator.model}`\n"
                    f"❌ 错误详情: {self.evaluator.last_error}\n\n"
                    "📌 处理: 本轮已自动降级为规则启发式评分。\n"
                    "💡 建议: 在微信回复 `/llm model` 检查模型连通性，或回复 `/llm model <新模型>` 切换可用模型！"
                )
            )


        notified = False
        if res.need_notify:
            if is_in_quiet_hours(self.quiet_hours):
                logger.info(f"[{item.platform}] 当前处于夜间免打扰时段 ({self.quiet_hours})，静默记录不推送: {item.title[:30]}")
            else:
                tags_str = " ".join([f"`{t}`" for t in res.tags]) if res.tags else ""
                btn_text = "查看知乎回答" if item.platform == "zhihu" else "查看原文"

                # 取 item_id 简短标识（如知乎回答 ID 或哈希）
                item_ref = item.item_id.split("_")[-1] if "_" in item.item_id else item.item_id[:12]

                # 1. 微信原生卡片内容
                title = f"📡 发现高价值内容({res.value_score}分) [ID:{item_ref}]"
                summary = f"平台: {item.platform.upper()} | 动态: {item.action}"
                details = f"<b>📌 议题</b>: {item.title}<br/>" \
                          f"<b>👤 答主</b>: {item.author} (👍 {item.upvotes})<br/>" \
                          f"<b>💡 核心见解</b>: {res.core_insight}<br/>" \
                          f"<b>🎯 推荐理由</b>: {res.value_reason}<br/>" \
                          f"<div class=\"gray\">标签: {' '.join(res.tags)}</div>" \
                          f"<div class=\"gray\">💬 追问提示: 回复 /llm {item_ref} 您的提问 或 /llm 提问</div>"

                # 2. 企微 Markdown 富文本内容
                md_content = f"""### 📡 发现高价值动态推荐 [ID: {item_ref}]
**议题**: [{item.title}]({item.url})
**动态**: {item.action} | **答主**: {item.author} (👍 **{item.upvotes}** 赞同)
**价值得分**: 🔥 **{res.value_score} 分** {tags_str}
> **💡 核心见解**: {res.core_insight}
> **🎯 推荐理由**: {res.value_reason}

[🔗 点击打开知乎查阅详情]({item.url})

💬 追问提示: 回复 `/llm {item_ref} 您的提问` 或 `/llm 您的提问` 展开深度探讨"""

                notified = self.notifier.send_dual_notification(
                    title=title,
                    summary=summary,
                    details=details,
                    markdown_content=md_content,
                    url=item.url,
                    btntxt=btn_text
                )

        # 记录入库去重
        self.storage.record_item(
            item_id=item.item_id,
            platform=item.platform,
            item_type=item.item_type,
            title=item.title,
            author=item.author,
            url=item.url,
            value_score=res.value_score,
            is_notified=notified,
            core_insight=res.core_insight
        )

    def poll_all_monitors(self):
        """遍历所有监控源执行一轮抓取与评估."""
        for monitor in self.monitors:
            p_name = monitor.get_platform_name()
            logger.info(f"[{p_name}] 正在执行动态检索...")
            try:
                items = monitor.fetch_new_items()
                for it in items:
                    self.process_item(it)
            except Exception as e:
                logger.error(f"[{p_name}] 抓取异常: {e}")
    def _start_command_server(self, port: int = 8085):
        """本地轻量 HTTP 端口接收来自微信回调网关的指令并执行."""
        import threading, json
        from urllib.parse import urlparse, parse_qs
        from http.server import HTTPServer, BaseHTTPRequestHandler

        service_ref = self

        class CmdHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)
                cmd_text = params.get("cmd", [""])[0]
                if cmd_text:
                    reply = service_ref.cmd_handler.handle_command(cmd_text)
                    service_ref.notifier.send_dual_notification(
                        title="⚙️ 社交雷达指令结果",
                        summary="指令交互调参",
                        details=reply.replace("\n", "<br/>"),
                        markdown_content=reply,
                        url="https://www.zhihu.com/follow",
                        btntxt="查看知乎"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(reply.encode("utf-8"))
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"SocialRadar Command Server Running")

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8", errors="replace")
                try:
                    data = json.loads(body)
                    cmd_text = data.get("command", "")
                    from_user = data.get("from_user", "@all")
                    reply = service_ref.cmd_handler.handle_command(cmd_text, from_user)
                    service_ref.notifier.send_dual_notification(
                        title="⚙️ 社交雷达指令结果",
                        summary="来自微信指令交互",
                        details=reply.replace("\n", "<br/>"),
                        markdown_content=reply,
                        url="https://www.zhihu.com/follow",
                        btntxt="查看知乎"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps({"code": 0, "reply": reply}, ensure_ascii=False).encode("utf-8"))
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(e).encode("utf-8"))

            def log_message(self, format, *args):
                pass

        def run_server():
            try:
                httpd = HTTPServer(("127.0.0.1", port), CmdHandler)
                logger.info(f"[Command] 社交雷达本地指令交互服务就绪: http://127.0.0.1:{port}")
                httpd.serve_forever()
            except Exception as e:
                logger.debug(f"[Command] 指令端口异常: {e}")

        t = threading.Thread(target=run_server, daemon=True)
        t.start()
    def run_forever(self):
        """主守护循环：长周期 + 拟人随机 Jitter 抖动，严密防范风控."""
        self.send_startup_message()
        logger.info(f"[SocialRadar] 启动常驻监控守护服务 (基础周期: {self.base_interval_minutes} 分钟, 抖动: ±{int(self.jitter_ratio*100)}%)...")

        while True:
            try:
                self.poll_all_monitors()
            except Exception as e:
                logger.error(f"[SocialRadar] 轮询主循环异常: {e}")

            # 计算拟人化随机等待时间
            jitter = random.uniform(-self.jitter_ratio, self.jitter_ratio)
            sleep_minutes = max(5, self.base_interval_minutes * (1 + jitter))
            sleep_seconds = int(sleep_minutes * 60)
            logger.info(f"[SocialRadar] 本轮检查完成，防爬安全休眠 {sleep_minutes:.1f} 分钟 ({sleep_seconds} 秒)...")
            time.sleep(sleep_seconds)
