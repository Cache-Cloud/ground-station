# Copyright (c) 2026 Efstratios Goudelis

import asyncio
from uuid import uuid4

import pytest

from handlers.entities import control


class _Sio:
    async def emit(self, *args, **kwargs):
        del args, kwargs


class _Logger:
    def info(self, *args, **kwargs):
        del args, kwargs


@pytest.mark.asyncio
async def test_full_backup_can_be_cancelled_by_its_owner(monkeypatch):
    """A cancellation RPC stops the matching in-flight export request."""
    started = asyncio.Event()

    async def _slow_full_backup(progress_callback=None):
        del progress_callback
        started.set()
        await asyncio.Event().wait()
        return {"success": True, "sql": "unreachable"}

    control._FULL_BACKUP_OPERATIONS.clear()
    monkeypatch.setattr(control, "full_backup", _slow_full_backup)
    operation_id = str(uuid4())
    backup_task = asyncio.create_task(
        control.backup_full_dump(_Sio(), {"operation_id": operation_id}, _Logger(), "owner-sid")
    )
    await started.wait()

    cancel_reply = await control.cancel_full_backup(
        _Sio(), {"operation_id": operation_id}, _Logger(), "owner-sid"
    )
    backup_reply = await backup_task

    assert cancel_reply == {
        "success": True,
        "operation_id": operation_id,
        "cancelling": True,
    }
    assert backup_reply == {"success": True, "cancelled": True}
    assert control._FULL_BACKUP_OPERATIONS == {}


@pytest.mark.asyncio
async def test_full_backup_cannot_be_cancelled_by_another_socket(monkeypatch):
    """Operation IDs are scoped to their initiating Socket.IO session."""
    started = asyncio.Event()

    async def _slow_full_backup(progress_callback=None):
        del progress_callback
        started.set()
        await asyncio.Event().wait()
        return {"success": True, "sql": "unreachable"}

    control._FULL_BACKUP_OPERATIONS.clear()
    monkeypatch.setattr(control, "full_backup", _slow_full_backup)
    operation_id = str(uuid4())
    backup_task = asyncio.create_task(
        control.backup_full_dump(_Sio(), {"operation_id": operation_id}, _Logger(), "owner-sid")
    )
    await started.wait()

    cancel_reply = await control.cancel_full_backup(
        _Sio(), {"operation_id": operation_id}, _Logger(), "other-sid"
    )
    assert cancel_reply["success"] is False

    backup_task.cancel()
    backup_reply = await backup_task
    assert backup_reply == {"success": True, "cancelled": True}
