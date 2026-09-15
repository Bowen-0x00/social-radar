"""X (Twitter) 平台监控适配器框架插槽 (架构预留，待账号就绪后激活)."""

from typing import List
from loguru import logger
from .base_monitor import BaseMonitor
from .models import SocialItem


class XMonitor(BaseMonitor):
    """X (Twitter) 平台监控器 (预留插槽)."""

    def __init__(
        self,
        enabled: bool = False,
        bearer_token: str = "",
        monitored_users: List[str] = None
    ):
        self.enabled = enabled and bool(bearer_token) and bearer_token != "YOUR_TWITTER_BEARER_TOKEN"
        self.bearer_token = bearer_token
        self.monitored_users = monitored_users or []

        if self.enabled:
            logger.info(f"[X-Monitor] X (Twitter) 监控已启用，监控目标用户: {self.monitored_users}")
        else:
            logger.debug("[X-Monitor] X (Twitter) 监控目前处于挂起状态 (等待账号配置)")

    def get_platform_name(self) -> str:
        return "x_twitter"

    def fetch_new_items(self) -> List[SocialItem]:
        """抓取关注推特用户的最新推文 (待配置 Bearer Token 后激活)."""
        if not self.enabled or not self.monitored_users:
            return []

        items: List[SocialItem] = []
        # TODO: 当用户提供 X Bearer Token 后，调用 Twitter v2 API:
        # 1. GET /2/users/by/username/{username} -> user_id
        # 2. GET /2/users/{user_id}/tweets?tweet.fields=created_at,public_metrics
        # 3. 组装为 SocialItem 并返回
        logger.debug("[X-Monitor] 正在检查 X 平台推文更新...")
        return items
