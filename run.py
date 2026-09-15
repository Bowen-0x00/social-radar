"""SocialRadar 命令行启动与调试入口."""

import argparse
from loguru import logger

from radar.service import SocialRadarService


def test_wechat_push(service: SocialRadarService):
    """测试企业微信通知通道."""
    logger.info("=== 测试企业微信 1000004 应用通知通道 ===")
    title = "📡 SocialRadar 社交雷达测试"
    summary = "微信双通道通知已成功联通！"
    details = "<b>应用名称</b>: 社交雷达 (1000004)<br/>" \
              "<b>当前状态</b>: 正常运行中<br/>" \
              "<b>监控目标</b>: 知乎关注动态与关注问题最新回答<br/>" \
              "<div class=\"highlight\">个人微信可直接查看此卡片，企微可查看完整Markdown排版！</div>"

    md_content = """### 📡 SocialRadar 社交雷达测试成功
**状态**: 微信双通道通知已打通！
**功能**:
- 🔍 知乎关注人动态雷达
- 📝 关注问题高质量新回答监听
- 🧠 LLM 价值深度打分与核心见解提炼
> 如能在微信收到此卡片，说明通知通道配置完全正确！"""

    ok = service.notifier.send_dual_notification(
        title=title,
        summary=summary,
        details=details,
        markdown_content=md_content,
        url="https://www.zhihu.com/follow",
        btntxt="打开知乎"
    )
    if ok:
        logger.success("测试消息已发送！请查看您的微信。")
    else:
        logger.error("测试消息发送失败，请检查配置。")


def test_zhihu_monitor(service: SocialRadarService):
    """测试知乎监控器抓取效果."""
    logger.info("=== 测试知乎动态抓取与 AI 评估 ===")
    for monitor in service.monitors:
        if monitor.get_platform_name() == "zhihu":
            items = monitor.fetch_new_items()
            logger.info(f"成功抓取到 {len(items)} 条知乎数据！")
            for it in items[:3]:
                logger.info(f"示例: [{it.action}] 《{it.title[:30]}》 - {it.author} ({it.url})")
            return
    logger.warning("未找到知乎监控器！")


def main():
    parser = argparse.ArgumentParser(description="SocialRadar - 社交前沿动态与高价值内容监控雷达")
    parser.add_argument("--test-wechat", action="store_true", help="测试企业微信连通性与发送通知")
    parser.add_argument("--test-zhihu", action="store_true", help="测试知乎数据抓取")
    parser.add_argument("--once", action="store_true", help="单次执行抓取与评估后退出")
    parser.add_argument("--interval", type=int, default=None, help="覆盖基础轮询周期 (分钟，默认 20)")

    args = parser.parse_args()

    service = SocialRadarService()

    if args.interval:
        service.base_interval_minutes = args.interval

    if args.test_wechat:
        test_wechat_push(service)
        return

    if args.test_zhihu:
        test_zhihu_monitor(service)
        return

    if args.once:
        logger.info("执行单次全平台扫描检查...")
        service.poll_all_monitors()
        logger.info("单次检查完成！")
        return

    # 默认常驻守护运行
    service.run_forever()


if __name__ == "__main__":
    main()
