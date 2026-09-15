"""监控器基类接口模块."""

from abc import ABC, abstractmethod
from typing import List
from .models import SocialItem


class BaseMonitor(ABC):
    """跨社交平台监控器抽象基类."""

    @abstractmethod
    def fetch_new_items(self) -> List[SocialItem]:
        """抓取并返回最新条目列表."""
        raise NotImplementedError

    @abstractmethod
    def get_platform_name(self) -> str:
        """返回平台名称标识."""
        raise NotImplementedError
