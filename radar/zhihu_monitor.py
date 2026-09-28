"""知乎动态与关注问题回答监控器 (具备防反爬虫拟人调度策略)."""

import time
import random
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional
from loguru import logger

from .base_monitor import BaseMonitor
from .models import SocialItem


class ZhihuMonitor(BaseMonitor):
    """知乎平台监控器 (关注人动态 + 关注问题最新回答)."""

    def __init__(
        self,
        cookie: str,
        user_token: str = "Bowen",
        check_moments: bool = True,
        check_questions: bool = True,
        max_questions_per_round: int = 8,
        delay_range: tuple = (2.5, 6.0),
        timeout: int = 15,
        notifier: Optional[Any] = None
    ):
        self.notifier = notifier
        self.cookie = cookie.strip()
        self.user_token = user_token.strip()
        self.check_moments = check_moments
        self.check_questions = check_questions
        self.max_questions_per_round = max_questions_per_round
        self.min_delay, self.max_delay = delay_range
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "accept": "*/*",
            "accept-language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "cache-control": "no-cache",
            "pragma": "no-cache",
            "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
            "x-requested-with": "fetch",
            "cookie": self.cookie
        })

    def get_platform_name(self) -> str:
        return "zhihu"

    def _sleep_jitter(self):
        """拟人化微休眠，防止高频请求触发知乎风控限制."""
        sleep_sec = random.uniform(self.min_delay, self.max_delay)
        logger.debug(f"[Zhihu] 防反爬安全休眠 {sleep_sec:.2f} 秒...")
        time.sleep(sleep_sec)

    def fetch_new_items(self) -> List[SocialItem]:
        """抓取并聚合最新知乎动态与关注问题的新回答."""
        all_items: List[SocialItem] = []

        # 1. 抓取“关注的人的动态”
        if self.check_moments:
            try:
                moments = self._fetch_moments(limit=12)
                all_items.extend(moments)
            except Exception as e:
                logger.error(f"[Zhihu] 抓取关注人动态异常: {e}")

        # 2. 抓取“关注的问题的最新回答”
        if self.check_questions:
            self._sleep_jitter()
            try:
                q_answers = self._fetch_following_questions_answers(max_q=self.max_questions_per_round)
                all_items.extend(q_answers)
            except Exception as e:
                logger.error(f"[Zhihu] 抓取关注问题回答异常: {e}")

        logger.info(f"[Zhihu] 本轮共抓取到 {len(all_items)} 条候选动态/回答")
        return all_items

    def _fetch_moments(self, limit: int = 12) -> List[SocialItem]:
        """抓取关注人的时间线动态 (api/v3/moments)."""
        url = f"https://www.zhihu.com/api/v3/moments?limit={limit}"
        self.session.headers["referer"] = "https://www.zhihu.com/follow"

        resp = self.session.get(url, timeout=self.timeout)
        if resp.status_code in (401, 403, 429):
            logger.warning(f"[Zhihu] 触发限流或验证码或凭据失效 (HTTP {resp.status_code})")
            if self.notifier:
                self.notifier.send_alert(
                    alert_key="social_radar_zhihu_cookie",
                    title="🍪 【社交雷达 - 知乎凭据失效告警】",
                    content=(
                        f"⚠️ 状态: 知乎动态接口返回 HTTP {resp.status_code} (凭据已失效或触发反爬拦截)。\n"
                        "雷达已暂停知乎内容抓取。\n"
                        "💡 恢复: 电脑登录知乎复制 Cookie，在微信回复 `/cookie <新Cookie>` 即可热更新恢复采集！"
                    )
                )
            return []
        if resp.status_code != 200:
            logger.warning(f"[Zhihu] 动态接口异常 HTTP {resp.status_code}")
            return []

        items: List[SocialItem] = []
        raw_data = resp.json().get("data", [])

        for it in raw_data:
            action_text = it.get("action_text", "")
            actor = it.get("actor", {}).get("name", "")
            target = it.get("target", {})
            if not target:
                continue

            target_type = target.get("type", "")
            target_id = target.get("id", "")
            if not target_id:
                continue

            # 区分问答与专栏文章
            title = ""
            content_snippet = ""
            author = ""
            upvotes = 0
            url = ""

            if target_type == "answer":
                q_info = target.get("question", {})
                title = q_info.get("title", "")
                author = target.get("author", {}).get("name", "匿名用户")
                excerpt = target.get("excerpt", "") or target.get("content", "")
                content_snippet = BeautifulSoup(excerpt, "html.parser").get_text(strip=True)
                upvotes = target.get("voteup_count", 0)
                qid = q_info.get("id", "")
                url = f"https://www.zhihu.com/question/{qid}/answer/{target_id}"
            elif target_type == "article":
                title = target.get("title", "")
                author = target.get("author", {}).get("name", "匿名用户")
                excerpt = target.get("excerpt", "") or target.get("content", "")
                content_snippet = BeautifulSoup(excerpt, "html.parser").get_text(strip=True)
                upvotes = target.get("voteup_count", 0)
                url = f"https://zhuanlan.zhihu.com/p/{target_id}"
            else:
                continue

            if not title:
                continue

            item_id = f"zhihu_moment_{it.get('id', target_id)}"
            items.append(SocialItem(
                item_id=item_id,
                platform="zhihu",
                item_type="moment",
                title=title,
                author=author,
                action=f"{actor} {action_text}".strip(),
                url=url,
                content_snippet=content_snippet[:600],
                upvotes=upvotes,
                comments_count=target.get("comment_count", 0),
                publish_time=target.get("created_time") or it.get("created_time", 0)
            ))

        return items

    def _fetch_following_questions_answers(self, max_q: int = 8) -> List[SocialItem]:
        """抓取关注的问题列表，并获取每个问题的最新回答."""
        q_url = f"https://www.zhihu.com/api/v4/members/{self.user_token}/following-questions?include=data%5B*%5D.created%2Canswer_count%2Cauthor&offset=0&limit={max_q}"
        self.session.headers["referer"] = f"https://www.zhihu.com/people/{self.user_token}/following/questions"

        resp = self.session.get(q_url, timeout=self.timeout)
        if resp.status_code != 200:
            logger.warning(f"[Zhihu] 获取关注问题列表失败 HTTP {resp.status_code}")
            return []

        questions = resp.json().get("data", [])
        logger.debug(f"[Zhihu] 检索到 {len(questions)} 个已关注问题")

        answer_items: List[SocialItem] = []
        for q in questions[:max_q]:
            qid = q.get("id")
            q_title = q.get("title", "")
            if not qid or not q_title:
                continue

            # 安全随机延迟，避免对知乎问答 API 产生爆发请求
            self._sleep_jitter()

            ans_url = f"https://www.zhihu.com/api/v4/questions/{qid}/answers?include=data%5B*%5D.content%2Cexcerpt%2Cvoteup_count%2Ccreated_time%2Cupdated_time%2Cauthor&limit=2&offset=0&sort_by=updated"
            self.session.headers["referer"] = f"https://www.zhihu.com/question/{qid}"

            try:
                a_resp = self.session.get(ans_url, timeout=self.timeout)
                if a_resp.status_code != 200:
                    continue

                answers = a_resp.json().get("data", [])
                for a in answers:
                    aid = a.get("id")
                    if not aid:
                        continue

                    author = a.get("author", {}).get("name", "匿名用户")
                    raw_text = a.get("excerpt", "") or a.get("content", "")
                    clean_text = BeautifulSoup(raw_text, "html.parser").get_text(strip=True)

                    answer_items.append(SocialItem(
                        item_id=f"zhihu_qans_{aid}",
                        platform="zhihu",
                        item_type="question_answer",
                        title=q_title,
                        author=author,
                        action="关注的问题有新回答",
                        url=f"https://www.zhihu.com/question/{qid}/answer/{aid}",
                        content_snippet=clean_text[:800],
                        upvotes=a.get("voteup_count", 0),
                        publish_time=a.get("updated_time") or a.get("created_time", 0)
                    ))
            except Exception as e:
                logger.warning(f"[Zhihu] 拉取问题 [{q_title[:20]}] 回答异常: {e}")

        return answer_items
