"""SocialRadar 单元与集成测试套件."""

import pytest
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from radar.models import SocialItem, EvaluationResult
from radar.storage import RadarStorage
from radar.llm_evaluator import LLMEvaluator


@pytest.fixture
def temp_storage(tmp_path):
    db_file = str(tmp_path / "test_radar.db")
    return RadarStorage(db_file)


def test_storage_deduplication(temp_storage):
    item_id = "zhihu_test_12345"
    assert not temp_storage.is_processed(item_id)

    temp_storage.record_item(
        item_id=item_id,
        platform="zhihu",
        item_type="question_answer",
        title="存算一体前景",
        author="测试答主",
        url="https://www.zhihu.com/question/123/answer/456",
        value_score=85,
        is_notified=True,
        core_insight="核心技术观点"
    )

    assert temp_storage.is_processed(item_id)


def test_heuristic_evaluator_high_value():
    evaluator = LLMEvaluator(
        base_url="",
        api_key="",
        profile_path="config/user_profile.yaml",
        min_value_score=70,
        enable=False
    )

    high_val_item = SocialItem(
        item_id="test_high_1",
        platform="zhihu",
        item_type="question_answer",
        title="大家对存算一体与CXL近存架构的前景怎么看？",
        author="体系结构专家",
        action="发布了回答",
        url="https://www.zhihu.com/question/123",
        content_snippet="在LLM推理场景下，访存墙瓶颈凸显，CXL近存计算和PIM架构是突破I/O复杂度的关键路径...",
        upvotes=120
    )

    res = evaluator.evaluate(high_val_item)
    assert res.value_score >= 70
    assert res.need_notify
    assert not res.is_noise


def test_heuristic_evaluator_noise():
    evaluator = LLMEvaluator(
        base_url="",
        api_key="",
        profile_path="config/user_profile.yaml",
        min_value_score=70,
        enable=False
    )

    noise_item = SocialItem(
        item_id="test_noise_1",
        platform="zhihu",
        item_type="moment",
        title="八卦：娱乐圈最新大瓜讨论",
        author="娱乐博主",
        action="赞同了回答",
        url="https://www.zhihu.com/question/999",
        content_snippet="今天我们来聊聊某个明星的绯闻八卦...",
        upvotes=5
    )

    res = evaluator.evaluate(noise_item)
    assert res.value_score < 70
    assert not res.need_notify


def test_model_switching_and_status(tmp_path):
    """测试 /llm model 查看状态与模型切换分支."""
    from radar.command_handler import RadarCommandHandler

    class MockEvaluator:
        enable = True
        model = "gemini-3.8-flash"
        base_url = "https://mock.api/v1"
        min_value_score = 70
        def test_model(self, m):
            if m == "good-model":
                return True, "0.3s"
            return False, "503 No Channel"

    class MockService:
        cfg = {"radar": {"quiet_hours": "off"}, "zhihu": {"cookie": ""}, "llm": {"model": "gemini-3.8-flash"}}
        max_days_back = 7
        base_interval_minutes = 20
        jitter_ratio = 0.3
        min_value_score = 70
        evaluator = MockEvaluator()
        storage = RadarStorage(str(tmp_path / "mock.db"))
        monitors = []

    handler = RadarCommandHandler.__new__(RadarCommandHandler)
    handler.service = MockService()
    handler._update_yaml = lambda k, v: None

    # 1. /llm model 查看状态
    res_view = handler.handle_command("/llm model")
    assert "SocialRadar 大模型状态看板" in res_view

    # 2. /llm model bad-model 切换失败
    res_bad = handler.handle_command("/llm model bad-model")
    assert "模型连通性测试失败" in res_bad
    assert handler.service.evaluator.model == "gemini-3.8-flash"

    # 3. /llm model good-model 切换成功
    res_good = handler.handle_command("/llm model good-model")
    assert "大模型切换成功" in res_good
    assert handler.service.evaluator.model == "good-model"

    # 4. /status 状态探测
    res_status = handler.handle_command("/status")
    assert "SocialRadar 当前运行状态看板" in res_status
    assert "good-model" in res_status
