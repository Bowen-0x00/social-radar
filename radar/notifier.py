"""企业微信应用消息双通道推送模块 (自建应用 1000004)."""

import time
import requests
from typing import Optional, Dict, Any
from loguru import logger


class WeChatNotifier:
    """企业微信自建应用通知推送器 (时序双通道：企微 Markdown + 个人微信 Textcard 卡片)."""

    def __init__(self, corp_id: str, agent_id: int, corp_secret: str, default_to_user: str = "@all"):
        self.corp_id = corp_id.strip()
        self.agent_id = int(agent_id)
        self.corp_secret = corp_secret.strip()
        self.default_to_user = default_to_user.strip() or "@all"
        self.alert_cooldowns: Dict[str, float] = {}

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    def send_alert(self, alert_key: str, title: str, content: str, to_user: Optional[str] = None, cooldown_seconds: int = 300) -> bool:
        """发送告警通知给用户，内置防刷屏冷却时间 (默认 5 分钟内同一类型告警仅发送一次)."""
        now = time.time()
        if not hasattr(self, "alert_cooldowns"):
            self.alert_cooldowns = {}
        last_time = self.alert_cooldowns.get(alert_key, 0.0)
        if now - last_time < cooldown_seconds:
            logger.debug(f"[Alert] 告警 [{alert_key}] 处于冷却中，跳过重复提醒")
            return False

        self.alert_cooldowns[alert_key] = now
        full_text = f"{title}\n━━━━━━━━━━━━━━━━━━\n{content}"
        logger.warning(f"[Alert] 触发微信用户告警: {title}")
        return self.send_text(full_text, to_user=to_user)
    def get_access_token(self, force_refresh: bool = False) -> str:
        """获取 access_token 带本地过期缓存."""
        now = time.time()
        if not force_refresh and self._access_token and now < self._token_expires_at:
            return self._access_token

        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        params = {"corpid": self.corp_id, "corpsecret": self.corp_secret}

        try:
            resp = requests.get(url, params=params, timeout=10)
            data = resp.json()
            if data.get("errcode") != 0:
                raise RuntimeError(f"获取 Token 失败: {data.get('errmsg')} (代码: {data.get('errcode')})")

            self._access_token = data["access_token"]
            self._token_expires_at = now + data.get("expires_in", 7200) - 300
            logger.debug("[WeChat] access_token 获取并缓存成功")
            return self._access_token
        except Exception as e:
            logger.error(f"[WeChat] 获取 access_token 异常: {e}")
            raise

    def send_dual_notification(
        self,
        title: str,
        summary: str,
        details: str,
        markdown_content: str,
        url: Optional[str] = None,
        btntxt: str = "查看详情"
    ) -> bool:
        """先发送 Markdown 富文本（供企微客户端享受最佳排版），再发送 Textcard（供个人微信原生完整展示）."""
        logger.info("[WeChat] 正在双通道推送 (1. 企微Markdown富文本 -> 2. 个人微信原生卡片)...")
        # 1. 先推 Markdown 给企微客户端
        ok_md = self.send_markdown(markdown_content)
        time.sleep(0.6)
        # 2. 后推 Textcard 给个人微信端
        description = f"<div class=\"gray\">{summary}</div><div class=\"normal\">{details}</div>"
        ok_card = self.send_card(title=title, description=description, url=url or "https://www.zhihu.com", btntxt=btntxt)
        return ok_md or ok_card

    def send_card(self, title: str, description: str, url: str, btntxt: str = "查看详情", to_user: Optional[str] = None) -> bool:
        """发送文本卡片消息 (个人微信原生完整支持)."""
        payload = {
            "title": title[:120],
            "description": description[:500],
            "url": url,
            "btntxt": btntxt[:8]
        }
        return self._send_message("textcard", payload, to_user)

    def _split_markdown_chunks(self, content: str, max_bytes: int = 1900) -> list:
        """将长 Markdown 在段落边界智能切片，严控单条在 1900 字节以内，避免企业微信截断."""
        if len(content.encode("utf-8")) <= max_bytes:
            return [content]

        paragraphs = content.split("\n\n")
        chunks = []
        current_chunk = ""

        for p in paragraphs:
            candidate = f"{current_chunk}\n\n{p}" if current_chunk else p
            if len(candidate.encode("utf-8")) <= max_bytes:
                current_chunk = candidate
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                if len(p.encode("utf-8")) > max_bytes:
                    lines = p.split("\n")
                    sub_chunk = ""
                    for line in lines:
                        sub_cand = f"{sub_chunk}\n{line}" if sub_chunk else line
                        if len(sub_cand.encode("utf-8")) <= max_bytes:
                            sub_chunk = sub_cand
                        else:
                            if sub_chunk:
                                chunks.append(sub_chunk)
                            sub_chunk = line
                    current_chunk = sub_chunk
                else:
                    current_chunk = p
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def send_markdown(self, content: str, to_user: Optional[str] = None) -> bool:
        chunks = self._split_markdown_chunks(content, max_bytes=1900)
        success = True
        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(0.5)
                chunk = f"> *(接上条...)*\n\n{chunk}"
            ok = self._send_message("markdown", {"content": chunk}, to_user)
            success = success and ok
        return success

    def send_text(self, content: str, to_user: Optional[str] = None) -> bool:
        chunks = self._split_markdown_chunks(content, max_bytes=1900)
        success = True
        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(0.5)
                chunk = f"(接上条...)\n{chunk}"
            ok = self._send_message("text", {"content": chunk}, to_user)
            success = success and ok
        return success

    def _send_message(self, msgtype: str, payload: Dict[str, Any], to_user: Optional[str] = None) -> bool:
        """底层消息发送逻辑."""
        token = self.get_access_token()
        target_user = to_user or self.default_to_user

        send_url = f"https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token={token}"
        body = {
            "touser": target_user,
            "msgtype": msgtype,
            "agentid": self.agent_id,
            msgtype: payload,
            "safe": 0,
            "enable_id_trans": 0,
            "enable_duplicate_check": 0
        }

        try:
            resp = requests.post(send_url, json=body, timeout=10)
            result = resp.json()
            err_code = result.get("errcode")
            if err_code == 0:
                logger.info(f"[WeChat] 微信通知推送成功 ({msgtype}) -> {target_user}")
                return True
            if err_code in (40014, 42001, 41001):
                logger.warning(f"[WeChat] Token 失效 ({err_code})，尝试强制刷新后重发...")
                self.get_access_token(force_refresh=True)
                return self._send_message(msgtype, payload, to_user)

            logger.error(f"[WeChat] 发送消息失败 [code {err_code}]: {result.get('errmsg')}")
            return False
        except Exception as e:
            logger.error(f"[WeChat] 发送消息网络异常: {e}")
            return False
