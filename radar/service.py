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
                delay_range=tuple(zc.get("request_delay_range", [2.5, 6.0]))
            ))

        xc = self.cfg.get("x_twitter", {})
        self.monitors.append(XMonitor(
            enabled=bool(xc.get("enabled", False)),
            bearer_token=xc.get("bearer_token", ""),
            monitored_users=xc.get("monitored_users", [])
        ))

    def send_startup_message(self):
        """发送服务启动与监听范围通知到微信."""
        platforms = [m.get_platform_name() for m in self.monitors]
        title = "📡 SocialRadar 社交动态雷达已就绪"
        summary = f"状态: 🟢 运行中 | 监控平台: {', '.join(platforms)}"

        details = f"<b>监控重点</b>: 关注人动态 + 关注问题最新回答<br/>" \
                  f"<b>基础周期</b>: {self.base_interval_minutes} 分钟 (随机抖动 ±{int(self.jitter_ratio*100)}%)<br/>" \
                  f"<b>推送阈值</b>: ≥ {self.min_value_score} 分 (大模型自动降噪过滤水帖)<br/>" \
                  f"<b>关注画像</b>: 体系结构、存算一体、CXL、AI加速器、RISC-V<br/>" \
                  f"<div class=\"highlight\">发现高价值动态将自动推送卡片与核心速读！</div>"

        md_content = f"""### 📡 SocialRadar 社交雷达服务已就绪！
**状态**: 🟢 正常运行中 (拟人随机长周期轮询)
**监控平台**: {', '.join(platforms)}
**轮询策略**: 基础周期 {self.base_interval_minutes} 分钟 (±{int(self.jitter_ratio*100)}% Jitter 动态随机)
**价值阈值**: 🔥 **{self.min_value_score} 分** 及以上推送 (自动过滤水帖段子)
**大模型**: {self.cfg['llm']['model']}

> 💡 **防封机制**: 每次轮询间隔随机浮动在 14~26 分钟，各请求之间随机延迟 2~6 秒，严防高频反爬封号！"""

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

        notified = False
        if res.need_notify:
            tags_str = " ".join([f"`{t}`" for t in res.tags]) if res.tags else ""
            btn_text = "查看知乎回答" if item.platform == "zhihu" else "查看原文"

            # 1. 微信原生卡片内容
            title = f"📡 发现高价值内容({res.value_score}分)"
            summary = f"平台: {item.platform.upper()} | 动态: {item.action}"
            details = f"<b>📌 议题</b>: {item.title}<br/>" \
                      f"<b>👤 答主</b>: {item.author} (👍 {item.upvotes})<br/>" \
                      f"<b>💡 核心见解</b>: {res.core_insight}<br/>" \
                      f"<b>🎯 推荐理由</b>: {res.value_reason}<br/>" \
                      f"<div class=\"gray\">标签: {' '.join(res.tags)}</div>"

            # 2. 企微 Markdown 富文本内容
            md_content = f"""### 📡 发现高价值动态推荐
**议题**: [{item.title}]({item.url})
**动态**: {item.action} | **答主**: {item.author} (👍 **{item.upvotes}** 赞同)
**价值得分**: 🔥 **{res.value_score} 分** {tags_str}
> **💡 核心见解**: {res.core_insight}
> **🎯 推荐理由**: {res.value_reason}

[🔗 点击打开知乎查阅详情]({item.url})"""

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
