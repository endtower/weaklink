"""Verify fail-closed event chains without platform or model calls."""
import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from workspace_layout import test_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {"ABYSS_DATA_DIR": str(test_root()), "LOG_GLOBAL_FILE": "0"}):
    from adapt.bridge.contract import SendReceipt
    from adapt.protocol import OutboundPayload, OutboundTarget, Platform, SessionScope
    from adapt.router import OutboundRouter
    from brain.att.station import AttentionStation
    from brain.base.heavy_agent.heavy_session import HeavySession
    from config.settings import safety_config
    from utils.chain_context import (
        ChainAbortedError, abort_current_chain, ensure_chain_active, get_chain_context,
        reset_chain_context, set_chain_context,
    )
    from utils.error_handling import NetworkError, ValidationError, async_handle_errors, handle_errors


class ErrorBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_handled_fallback_is_returned_and_typed_failure_stops_chain(self):
        @handle_errors(raise_on=None, default_return="fallback")
        def recover():
            raise ValidationError("recoverable fixture")

        @async_handle_errors(raise_on=None, default_return=False)
        async def recover_async():
            raise ValidationError("recoverable async fixture")

        @async_handle_errors()
        async def fail():
            raise ValidationError("rejected fixture")

        token = set_chain_context("failed-operation")
        try:
            self.assertEqual(recover(), "fallback")
            self.assertIs(await recover_async(), False)
            ensure_chain_active()
            captured = get_chain_context()
            with self.assertRaises(ValidationError):
                await fail()
        finally:
            reset_chain_context(token)

        # Delayed workers must carry the failed state even after the owner resets its context.
        token = set_chain_context(captured)
        try:
            with self.assertRaises(ChainAbortedError):
                ensure_chain_active()
        finally:
            reset_chain_context(token)
        ensure_chain_active()

    async def test_unknown_delivery_stops_followup_tool_and_repeat_send_in_same_chain(self):
        router = OutboundRouter()
        channel = SimpleNamespace(send=AsyncMock(return_value=SendReceipt("request", "unknown")))
        router._channels[Platform.WECHAT] = channel
        target = OutboundTarget(SessionScope.PRIVATE, "12345")
        payload = OutboundPayload.text("fixture")
        later_tool = AsyncMock()

        async def tool(call):
            if call.function.name == "send_message":
                return await router.send(Platform.WECHAT, target, payload)
            await later_tool()

        calls = [SimpleNamespace(function=SimpleNamespace(name=name))
                 for name in ("send_message", "follow_up")]
        session = SimpleNamespace(
            _rounds=0,
            max_no_tool_call=None,
            max_tool_error=None,
            _inject_first_user_message=AsyncMock(),
            _call_llm=AsyncMock(return_value=SimpleNamespace(tool_calls=calls)),
            _write_assistant_message=Mock(),
            _register_tool_call=Mock(return_value="ok"),
            _handle_tool_call=tool,
            _should_append_tool_response=Mock(return_value=False),
        )
        token = set_chain_context("uncertain-send")
        try:
            with patch.object(safety_config, "SIMULATED_SEND", False):
                with self.assertRaises(ChainAbortedError):
                    await HeavySession.process_cycle(session)
                with self.assertRaises(ChainAbortedError):
                    await router.send(Platform.WECHAT, target, payload)
        finally:
            reset_chain_context(token)
        channel.send.assert_awaited_once()
        later_tool.assert_not_awaited()

    async def test_station_processes_a_different_event_after_an_operation_failure(self):
        ran = asyncio.Event()

        async def rejected():
            abort_current_chain()
            raise NetworkError("fixture service unavailable")

        async def independent():
            ensure_chain_active()
            ran.set()
            return None

        station = AttentionStation.__new__(AttentionStation)
        station.running = True
        station.task_queue = asyncio.Queue()
        station._enqueued_truck_ids = set()
        trucks = {
            "failed": SimpleNamespace(truck_id="failed", state="running", get_truck_messages=rejected),
            "independent": SimpleNamespace(truck_id="independent", state="running", get_truck_messages=independent),
        }
        station._get_truck = trucks.get
        station._all_running_trucks = lambda: []
        for name in trucks:
            station.task_queue.put_nowait(name)
        with patch("brain.att.station._force_archive_chain_contexts"):
            worker = asyncio.create_task(station._process_tasks())
            try:
                await asyncio.wait_for(station.task_queue.join(), 5)
                self.assertTrue(ran.is_set())
                self.assertFalse(worker.done())
            finally:
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)


if __name__ == "__main__":
    unittest.main()
