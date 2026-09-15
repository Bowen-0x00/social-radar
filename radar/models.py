"""社交雷达统一数据模型模块."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class SocialItem:
    """标准化的社交动态与讨论条目."""
    item_id: str                   # 唯一标识，用于数据库幂等去重 (如 zhihu_ans_12345)
    platform: str                  # 'zhihu' 或 'x_twitter'
    item_type: str                 # 'moment' (动态/赞同), 'question_answer' (问题新回答), 'tweet'
    title: str                     # 问题标题 / 动态主题 / 问答标题
    author: str                    # 作者 / 答主 / 发帖人
    action: str                    # 触发行为：'赞同了回答', '发布了回答', '关注了问题'
    url: str                       # 原文链接
    content_snippet: str           # 正文片段 / 摘要
    upvotes: int = 0               # 点赞/赞同数
    comments_count: int = 0        # 评论数
    publish_time: int = 0          # 产生时间戳
    extra_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationResult:
    """大语言模型价值评估结果."""
    item_id: str
    value_score: int               # 0-100 价值评分
    need_notify: bool              # 是否达到阈值应当推送
    core_insight: str              # 1-2 句话提炼核心观点/创新见解
    value_reason: str              # 推荐理由 / 为什么值得一读
    tags: List[str]                # 标签列表，如 ['#体系结构', '#存算一体']
    is_noise: bool = False         # 是否判定为水帖/纯情绪发泄/娱乐八卦
