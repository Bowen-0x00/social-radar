"""大语言模型内容价值深度评估与智能降噪过滤 Agent."""

import re
import json
import yaml
import httpx
from typing import Dict, Any, List, Optional
from openai import OpenAI
from loguru import logger

from .models import SocialItem, EvaluationResult


class LLMEvaluator:
    """基于大模型的内容价值甄别器 (识别体系结构/芯片/软硬件深度前沿，过滤口水娱乐帖)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gemini-3.8-flash",
        temperature: float = 0.2,
        proxy: Optional[str] = None,
        profile_path: str = "config/user_profile.yaml",
        min_value_score: int = 70,
        enable: bool = True
    ):
        self.enable = enable and bool(api_key) and api_key != "YOUR_LLM_API_KEY"
        self.model = model
        self.temperature = temperature
        self.min_value_score = min_value_score
        self.profile = self._load_profile(profile_path)

        self.client: Optional[OpenAI] = None
        if self.enable:
            http_client = httpx.Client(timeout=45.0, proxy=proxy) if proxy else httpx.Client(timeout=45.0)
            self.client = OpenAI(
                base_url=base_url,
                api_key=api_key,
                http_client=http_client
            )
            logger.info(f"[Evaluator] LLM 价值评估引擎就绪 (模型: {model}, 代理: {proxy or '直连'})")
        else:
            logger.warning("[Evaluator] LLM 引擎停用或未配置 API Key，将采用规则降级评估")

    def _load_profile(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"[Evaluator] 加载用户画像失败 ({path}): {e}")
            return {}

    def evaluate(self, item: SocialItem) -> EvaluationResult:
        """对动态或回答进行多维度价值评测与降噪."""
        if self.enable and self.client:
            res = self._evaluate_with_llm(item)
            if res:
                return res

        return self._heuristic_evaluate(item)

    def _evaluate_with_llm(self, item: SocialItem) -> Optional[EvaluationResult]:
        targets_desc = "\n".join([f"- {t}" for t in self.profile.get("target_topics", [])])
        keywords_desc = ", ".join(self.profile.get("keywords", []))
        excludes_desc = "\n".join([f"- {e}" for e in self.profile.get("exclude_patterns", [])])

        system_prompt = f"""你是一位敏锐的计算机体系结构资深研究员与技术雷达首席分析师。
请阅读用户在知乎或社交平台关注的人发布的动态或最新回答，评估其【对当前技术研究者的专业参考价值】，并严格过滤无营养的口水灌水内容。

【用户重点关注的研究领域】
{targets_desc}

【强相关核心技术关键词】
{keywords_desc}

【严厉降噪/一票否决的排除领域】
{excludes_desc}

【评分与判定标准 (0-100分)】:
- 85-100分 (极高价值/必读): 针对体系结构、存算一体(PIM/PNM)、CXL近存、大模型AI加速器芯片、编译器、RISC-V/向量架构有深度推导、真实流片/实测数据或深刻权衡(Trade-off)分析。
- 70-84分 (高价值/推荐): 有明确技术干货、专业行业动态或高质量深度讨论。
- 40-69分 (普通内容): 泛计算机科普、普通新闻转述、常规观点，无需专门打扰。
- 0-39分 (纯噪音/水帖): 影视娱乐八卦、无营养玩梗段子、纯情绪撕逼吐槽。直接标记 is_noise: true。

请严格输出标准 JSON 格式：
{{
  "value_score": 0到100的整数,
  "is_noise": true 或 false,
  "core_insight": "1~2句话精炼提炼作者的核心观点、论据或技术亮点",
  "value_reason": "说明为什么值得关注，或与用户研究方向有何启发",
  "tags": ["#标签1", "#标签2"]
}}"""

        user_prompt = f"""平台: {item.platform}
类型: {item.item_type} ({item.action})
主题/问题: {item.title}
作者/答主: {item.author} (赞同: {item.upvotes})
链接: {item.url}

内容截取:
{item.content_snippet[:3500]}"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            raw = response.choices[0].message.content or "{}"
            data = self._parse_json(raw)

            score = int(data.get("value_score", 40))
            is_noise = bool(data.get("is_noise", False))
            need_notify = (score >= self.min_value_score) and not is_noise
            tags = [t if t.startswith("#") else f"#{t}" for t in data.get("tags", [])]

            return EvaluationResult(
                item_id=item.item_id,
                value_score=score,
                need_notify=need_notify,
                core_insight=data.get("core_insight", ""),
                value_reason=data.get("value_reason", ""),
                tags=tags[:3],
                is_noise=is_noise
            )
        except Exception as e:
            logger.error(f"[Evaluator] 大模型评估异常: {e}")
            return None

    def _heuristic_evaluate(self, item: SocialItem) -> EvaluationResult:
        """基于关键词与赞同数的快速规则降级评分."""
        combined = f"{item.title} {item.content_snippet}".lower()
        matched = [kw for kw in self.profile.get("keywords", []) if kw.lower() in combined]

        score = 30
        if matched:
            score += min(len(matched) * 15, 50)
        if item.upvotes > 50:
            score += 15

        need_notify = score >= self.min_value_score
        return EvaluationResult(
            item_id=item.item_id,
            value_score=score,
            need_notify=need_notify,
            core_insight=item.content_snippet[:120] + "...",
            value_reason=f"命中关键词: {', '.join(matched)}" if matched else "常规关注动态",
            tags=matched[:2] if matched else ["#关注动态"],
            is_noise=len(matched) == 0 and score < 40
        )

    def _parse_json(self, text: str) -> Dict[str, Any]:
        text = text.strip()
        m = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if m:
            text = m.group(1).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m2 = re.search(r'\{[\s\S]*\}', text)
            if m2:
                try:
                    return json.loads(m2.group(0))
                except Exception:
                    pass
            return {}
