"""Exercise SQLite repository ownership and concurrent writes with temporary databases."""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workspace_layout import test_root

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
with patch.dict(os.environ, {"ABYSS_DATA_DIR": str(test_root()), "LOG_GLOBAL_FILE": "0"}):
    from memory.message_repository import MessageRepository
    from utils.error_handling import StorageError, ValidationError


def message(session_id, platform=None):
    session = {"session_id": session_id}
    if platform:
        session.update(platform=platform, connection_id=platform, remote_session_id=session_id)
    return {
        "session_info": session,
        "message_list": [{"message_id": "1", "timestamp": 1, "content_text": "fixture"}],
    }


class MessageRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=test_root())
        self.addCleanup(self.temp.cleanup)
        self.repo = MessageRepository(self.temp.name)
        self.addAsyncCleanup(self.repo.close)

    async def test_concurrent_initialization(self):
        original = self.repo._create_tables
        initializations = 0

        async def create(conn):
            nonlocal initializations
            initializations += 1
            await asyncio.sleep(0)
            await original(conn)

        with patch.object(self.repo, "_create_tables", side_effect=create):
            await asyncio.gather(*(self.repo.list_sessions() for _ in range(8)),
                                 self.repo.ensure_ready(), self.repo.ensure_ready())
        self.assertEqual(initializations, 1)
        await self.repo.close()
        with self.assertRaises(StorageError):
            await self.repo.list_sessions()

    async def test_failed_write_is_invisible_and_cannot_be_committed_by_another_save(self):
        partial_write = asyncio.Event()
        release = asyncio.Event()
        original = self.repo._insert_messages

        async def insert(conn, session_id, messages):
            if session_id == "private_100":
                partial_write.set()
                await release.wait()
                raise ValidationError("fixture write fails after inserting the session")
            return await original(conn, session_id, messages)

        with patch.object(self.repo, "_insert_messages", side_effect=insert):
            saves = [asyncio.create_task(self.repo.store_message(message("private_100")))]
            try:
                await asyncio.wait_for(partial_write.wait(), 5)
                successful = asyncio.create_task(self.repo.store_message(message("private_200")))
                saves.append(successful)
                self.assertFalse(await self.repo.session_exists("private_100"))
                self.assertFalse(successful.done())
            finally:
                release.set()
                results = await asyncio.gather(*saves, return_exceptions=True)
        self.assertIsInstance(results[0], ValidationError)
        self.assertEqual(results[1]["status"], "success")
        self.assertFalse(await self.repo.session_exists("private_100"))
        self.assertTrue(await self.repo.session_exists("private_200"))

    async def test_cancelled_write_rolls_back_before_switching_database(self):
        partial_write = asyncio.Event()

        async def insert(conn, session_id, messages):
            partial_write.set()
            await asyncio.Future()

        with patch.object(self.repo, "_insert_messages", side_effect=insert):
            save = asyncio.create_task(self.repo.store_message(message("private_100")))
            await asyncio.wait_for(partial_write.wait(), 5)
            save.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await save
        self.assertFalse(await self.repo.session_exists("private_100"))
        await self.repo.reconfigure(self.temp.name, "other.db")
        self.assertEqual((await self.repo.store_message(message("private_200")))["status"], "success")

    async def test_route_is_preserved_across_independent_connections(self):
        peer = MessageRepository(self.temp.name)
        self.addAsyncCleanup(peer.close)
        await asyncio.gather(self.repo.ensure_ready(), peer.ensure_ready())
        results = await asyncio.gather(
            self.repo.store_message(message("private_100", "qq")),
            peer.store_message(message("private_100", "wechat")),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(result, ValidationError) for result in results), 1)
        winner = "wechat" if isinstance(results[0], ValidationError) else "qq"
        self.assertEqual((await self.repo.session_route("private_100"))["platform"], winner)


if __name__ == "__main__":
    unittest.main()
