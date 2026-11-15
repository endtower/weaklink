"""Reflection and Quest contracts after maintenance actions were centralized."""
import json
import logging
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from workspace_layout import test_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_sandbox = tempfile.TemporaryDirectory(prefix="reflection-", dir=test_root())
os.environ["ABYSS_DATA_DIR"] = _sandbox.name

from brain.amy.feedback_state import FeedbackState
from brain.base.common_ways.tool_task import ToolTask
from brain.base.light_agent.quest_agent import QuestAgent
from brain.pfc.reflection.reflection_tools import Reflection_tool_manager


class ReflectionAcceptance(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.manager = Reflection_tool_manager()
        self.feedback = FeedbackState(Path(_sandbox.name))
        feedback = patch("brain.amy.feedback_state._feedback_state", self.feedback)
        feedback.start()
        self.addCleanup(feedback.stop)
        self.focus = SimpleNamespace(_data={}, set_activity=Mock(), manager_pfca_actions=Mock())
        self.core = SimpleNamespace(stop=AsyncMock())
        for target, value in (
            ("brain.pfc.reflection.reflection_tools.get_global_session_state", self.focus),
            ("brain.hc.global_session_state.get_global_session_state", self.focus),
            ("brain.pfc.reflection.reflection_core.get_reflection_instance", self.core),
        ):
            replacement = patch(target, return_value=value)
            replacement.start()
            self.addCleanup(replacement.stop)

    async def test_maintenance_is_explicit_and_finalize_has_no_purpose_type(self):
        schemas = {s["function"]["name"]: s["function"] for s in self.manager.get_tools()}
        for name in ("quest_agent", "finalize_reflection"):
            self.assertNotIn("purpose_type", schemas[name]["parameters"]["properties"])
        actions = schemas["maintenance_action"]["parameters"]["properties"]["action"]["enum"]
        self.assertEqual(set(actions), {"申请维护", "尝试自修复", "情绪宣泄", "发布关系改进任务"})

    async def test_preview_then_confirm_handoff_does_not_change_feedback(self):
        before = self.feedback.snapshot()
        preview = await self.manager.finalize_reflection(True, "核实结论")
        self.assertTrue(preview["confirmation_required"])
        self.assertEqual(preview["pending_action"], {"enter_action": True, "action_purpose": "核实结论"})
        self.assertNotIn("pfc_handoff", self.focus._data)
        self.core.stop.assert_not_awaited()
        self.assertEqual(self.feedback.snapshot(), before)

        self.assertEqual(await self.manager.finalize_reflection(), "反思已结束。")
        self.assertEqual(self.focus._data["pfc_handoff"], {"state": "action", "purpose": "核实结论"})
        self.core.stop.assert_awaited_once_with(exit_reason="reflection_done")
        self.assertEqual(self.feedback.snapshot(), before)

    async def test_confirmation_can_cancel_previewed_action(self):
        await self.manager.finalize_reflection(True, "先预览")
        await self.manager.finalize_reflection(enter_action=False)
        self.assertNotIn("pfc_handoff", self.focus._data)
        self.core.stop.assert_awaited_once()

    async def test_invalid_intention_and_new_session_cannot_publish_old_preview(self):
        with self.assertRaises(ValueError):
            await self.manager.finalize_reflection(True, " ")
        self.core.stop.assert_not_awaited()
        await self.manager.finalize_reflection(True, "上一轮计划")
        self.manager._begin_session()
        fresh = await self.manager.finalize_reflection()
        self.assertTrue(fresh["confirmation_required"])
        self.assertFalse(fresh["pending_action"]["enter_action"])
        self.assertNotIn("pfc_handoff", self.focus._data)

    async def test_maintenance_dispatches_to_shared_service(self):
        request = {"action": "尝试自修复", "title": "复核", "reason": "存在误差", "plan": "检查", "verification": "复测"}
        registration = AsyncMock(return_value={"status": "registered"})
        with patch("brain.base.common_ways.tool_maintenance.CriticalActions", return_value=SimpleNamespace(register=registration)):
            result = await self.manager.handle_tool_call(SimpleNamespace(
                id="maintenance-call",
                function=SimpleNamespace(name="maintenance_action", arguments=json.dumps(request)),
            ))
        registration.assert_awaited_once_with(**request)
        self.assertEqual(json.loads(result["content"]), {"status": "registered"})
        self.core.stop.assert_not_awaited()
        self.assertNotIn("pfc_handoff", self.focus._data)

    async def test_quest_delegates_current_route_and_keeps_text_result(self):
        agent = SimpleNamespace(run=AsyncMock(return_value={"formatted_output": "原结论", "created_tasks": []}))
        with patch.object(ToolTask, "_get_quest_agent", return_value=agent):
            result = await self.manager.handle_tool_call(SimpleNamespace(
                id="quest-call",
                function=SimpleNamespace(name="quest_agent", arguments=json.dumps({
                    "title": "已核实", "task_id": "task-1", "action": "complete",
                })),
            ))
        self.assertEqual(result["content"], "原结论")
        agent.run.assert_awaited_once_with(
            title="已核实", context="", next_occurrence="", kind="onetime", task_id="task-1", action="complete",
        )

    async def test_real_quest_run_receipts_are_successful_and_request_scoped(self):
        agent = object.__new__(QuestAgent)
        agent._messages, agent._tools_called = [], []
        agent._final_text = ""
        agent._history = None
        agent._push = lambda message: agent._messages.append(message)
        agent.get_system_prompt = Mock(return_value="隔离提示词")
        agent._serialize_assistant_message = Mock(return_value={"role": "assistant", "content": "调用创建"})
        receipt = {
            "task_id": "new-1", "title": "验证任务",
            "context": "上下文", "next_occurrence": "2026-12-31T12:00:00",
        }
        agent.tool_functions = {"create_task": AsyncMock(return_value=receipt)}
        call = SimpleNamespace(id="create-1", function=SimpleNamespace(name="create_task", arguments="{}"))
        finish = SimpleNamespace(id="finish-1", function=SimpleNamespace(name="finish", arguments="{}"))
        agent._finish_impl = AsyncMock(return_value={"status": "finished", "summary": ""})
        agent.tool_functions["finish"] = agent._finish_impl
        def reply(calls):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="完成", tool_calls=calls))])
        agent._call_llm = AsyncMock(side_effect=[reply([call]), reply([finish]), reply([finish])])
        with patch("brain.base.light_agent.quest_agent.new_light_history_manager", return_value=Mock()), \
             patch("brain.hc.database.task.TaskOperations.format_active_task_overview",
                   AsyncMock(return_value="无")), \
             patch("utils.chain_context.get_current_chain_id", return_value=None):
            first = await agent.run("创建验证任务", "上下文", "2026-12-31T12:00:00")
            second = await agent.run("只咨询", "上下文", "2026-12-31T12:00:00")
        self.assertEqual(first["created_tasks"], [receipt])
        self.assertEqual(second["created_tasks"], [])
        self.assertEqual([c["tool"] for c in second["tools_called"]], ["finish"])



if __name__ == "__main__":
    try:
        unittest.main(verbosity=2)
    finally:
        logging.shutdown()
        _sandbox.cleanup()
