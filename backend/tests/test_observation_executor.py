# Copyright (c) 2026 Efstratios Goudelis

import importlib
import sys
import types

import pytest

from observations.bundle import create_observation_bundle
from observations.constants import STATUS_FAILED


class _DummyAsyncSessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_observation(rotator=None):
    return {
        "id": "obs-1",
        "name": "Test observation",
        "enabled": True,
        "status": "scheduled",
        "satellite": {"name": "ISS", "norad_id": 25544, "group_id": "grp-1"},
        "rotator": rotator or {},
        "sessions": [
            {
                "sdr": {"id": "sdr-1"},
                "tasks": [{"type": "decoder", "config": {"transmitter_id": "tx-1"}}],
            }
        ],
    }


def _patch_common_start_dependencies(monkeypatch, executor_module, observation, tmp_path):
    async def _fetch_observation(_session, _observation_id):
        return {"success": True, "data": observation}

    async def _noop(*_args, **_kwargs):
        return None

    monkeypatch.setattr(executor_module, "AsyncSessionLocal", lambda: _DummyAsyncSessionContext())
    monkeypatch.setattr(executor_module, "fetch_scheduled_observations", _fetch_observation)
    monkeypatch.setattr(executor_module, "log_execution_event", _noop)
    monkeypatch.setattr(executor_module, "update_observation_status", _noop)
    monkeypatch.setattr(executor_module, "remove_scheduled_stop_job", _noop)
    monkeypatch.setattr(
        executor_module.session_tracker,
        "get_sessions_for_sdr",
        lambda _sdr_id: [],
    )
    monkeypatch.setattr(
        executor_module,
        "create_observation_bundle",
        lambda observation_id, satellite, _backend_dir: create_observation_bundle(
            observation_id, satellite, tmp_path
        ),
    )


def _new_executor(executor_module):
    dummy_process_manager = types.SimpleNamespace()
    return executor_module.ObservationExecutor(process_manager=dummy_process_manager, sio=None)


def _load_executor_module(monkeypatch):
    tasks_pkg = types.ModuleType("tasks")
    tasks_pkg.__path__ = []  # Make it behave like a package for "tasks.registry" resolution.
    registry_mod = types.ModuleType("tasks.registry")
    registry_mod.get_task = lambda _task_name: None

    monkeypatch.setitem(sys.modules, "tasks", tasks_pkg)
    monkeypatch.setitem(sys.modules, "tasks.registry", registry_mod)

    module = importlib.import_module("observations.executor")
    return importlib.reload(module)


@pytest.mark.asyncio
async def test_start_observation_starts_tracker_before_session_tasks(monkeypatch, tmp_path):
    executor_module = _load_executor_module(monkeypatch)
    observation = _build_observation()
    _patch_common_start_dependencies(monkeypatch, executor_module, observation, tmp_path)

    executor = _new_executor(executor_module)
    events = []

    async def _mock_start_tracker(*_args, **_kwargs):
        events.append("tracker")
        return {
            "success": True,
            "tracker_id": "target-1",
            "created": True,
            "reused_existing": False,
            "ephemeral": True,
        }

    async def _mock_execute_session(*_args, **_kwargs):
        events.append("session")

    monkeypatch.setattr(executor.tracker_handler, "start_tracker_task", _mock_start_tracker)
    monkeypatch.setattr(executor, "_execute_observation_session", _mock_execute_session)

    result = await executor.start_observation("obs-1")

    assert result["success"] is True
    assert events == ["tracker", "session"]
    assert executor._tracker_context_by_observation["obs-1"]["tracker_id"] == "target-1"


@pytest.mark.asyncio
async def test_start_observation_skips_bundle_for_disposable_satdump_iq_only(monkeypatch, tmp_path):
    executor_module = _load_executor_module(monkeypatch)
    observation = _build_observation()
    observation["sessions"][0]["tasks"] = [
        {
            "type": "iq_recording",
            "config": {
                "enable_post_processing": True,
                "post_process_pipeline": "meteor_m2-x_lrpt",
                "delete_after_post_processing": True,
            },
        }
    ]
    _patch_common_start_dependencies(monkeypatch, executor_module, observation, tmp_path)

    executor = _new_executor(executor_module)

    async def _mock_start_tracker(*_args, **_kwargs):
        return {"success": True, "tracker_id": "target-1"}

    async def _mock_execute_session(*_args, **_kwargs):
        return None

    def _unexpected_bundle(*_args, **_kwargs):
        raise AssertionError("disposable SatDump-only observation must not create a bundle")

    monkeypatch.setattr(executor.tracker_handler, "start_tracker_task", _mock_start_tracker)
    monkeypatch.setattr(executor, "_execute_observation_session", _mock_execute_session)
    monkeypatch.setattr(executor_module, "create_observation_bundle", _unexpected_bundle)

    result = await executor.start_observation("obs-1")

    assert result["success"] is True
    assert "obs-1" not in executor._bundle_dirs


def test_requires_observation_bundle_for_retained_or_mixed_artifacts(monkeypatch):
    executor_module = _load_executor_module(monkeypatch)

    disposable_iq = {
        "type": "iq_recording",
        "config": {
            "enable_post_processing": True,
            "post_process_pipeline": "meteor_m2-x_lrpt",
            "delete_after_post_processing": True,
        },
    }

    assert (
        executor_module.ObservationExecutor._requires_observation_bundle(
            [{"tasks": [disposable_iq]}]
        )
        is False
    )
    assert (
        executor_module.ObservationExecutor._requires_observation_bundle(
            [
                {
                    "tasks": [
                        {
                            **disposable_iq,
                            "config": {
                                **disposable_iq["config"],
                                "delete_after_post_processing": False,
                            },
                        }
                    ]
                }
            ]
        )
        is True
    )
    assert (
        executor_module.ObservationExecutor._requires_observation_bundle(
            [{"tasks": [disposable_iq, {"type": "decoder", "config": {}}]}]
        )
        is True
    )


@pytest.mark.asyncio
async def test_start_observation_fails_fast_when_tracker_start_fails(monkeypatch, tmp_path):
    executor_module = _load_executor_module(monkeypatch)
    observation = _build_observation()
    _patch_common_start_dependencies(monkeypatch, executor_module, observation, tmp_path)

    executor = _new_executor(executor_module)
    session_started = {"value": False}
    status_updates = []

    async def _mock_start_tracker(*_args, **_kwargs):
        return {
            "success": False,
            "error": "missing_target",
            "message": "Tracker target missing",
        }

    async def _mock_execute_session(*_args, **_kwargs):
        session_started["value"] = True

    async def _mock_update_status(_sio, _observation_id, status, *_args, **_kwargs):
        status_updates.append(status)

    monkeypatch.setattr(executor.tracker_handler, "start_tracker_task", _mock_start_tracker)
    monkeypatch.setattr(executor, "_execute_observation_session", _mock_execute_session)
    monkeypatch.setattr(executor_module, "update_observation_status", _mock_update_status)

    result = await executor.start_observation("obs-1")

    assert result["success"] is False
    assert session_started["value"] is False
    assert STATUS_FAILED in status_updates
    assert "obs-1" not in executor._running_observations


@pytest.mark.asyncio
async def test_start_observation_cleans_up_tracker_when_session_start_raises(monkeypatch, tmp_path):
    executor_module = _load_executor_module(monkeypatch)
    observation = _build_observation()
    _patch_common_start_dependencies(monkeypatch, executor_module, observation, tmp_path)

    executor = _new_executor(executor_module)
    stop_calls = []

    async def _mock_start_tracker(*_args, **_kwargs):
        return {
            "success": True,
            "tracker_id": "target-7",
            "created": True,
            "reused_existing": False,
            "ephemeral": True,
        }

    async def _mock_execute_session(*_args, **_kwargs):
        raise RuntimeError("session startup failed")

    async def _mock_stop_tracker(_observation_id, _rotator_config, tracker_context=None):
        stop_calls.append(tracker_context or {})
        return True

    monkeypatch.setattr(executor.tracker_handler, "start_tracker_task", _mock_start_tracker)
    monkeypatch.setattr(executor.tracker_handler, "stop_tracker_task", _mock_stop_tracker)
    monkeypatch.setattr(executor, "_execute_observation_session", _mock_execute_session)

    result = await executor.start_observation("obs-1")

    assert result["success"] is False
    assert len(stop_calls) == 1
    assert stop_calls[0]["tracker_id"] == "target-7"
    assert stop_calls[0]["ephemeral"] is True
    assert "obs-1" not in executor._tracker_context_by_observation


@pytest.mark.asyncio
async def test_stop_observation_task_passes_tracker_context_and_clears_it(monkeypatch):
    executor_module = _load_executor_module(monkeypatch)
    executor = _new_executor(executor_module)
    executor._tracker_context_by_observation["obs-1"] = {
        "tracker_id": "target-5",
        "ephemeral": True,
    }
    captured_context = {}

    async def _mock_stop_tracker(_observation_id, _rotator_config, tracker_context=None):
        captured_context.update(tracker_context or {})
        return True

    async def _mock_stop_session(*_args, **_kwargs):
        return None

    monkeypatch.setattr(executor.tracker_handler, "stop_tracker_task", _mock_stop_tracker)
    monkeypatch.setattr(executor, "_stop_observation_session", _mock_stop_session)

    await executor._stop_observation_task(
        "obs-1",
        {"satellite": {"name": "ISS"}, "sessions": [], "rotator": {}},
    )

    assert captured_context["tracker_id"] == "target-5"
    assert captured_context["ephemeral"] is True
    assert "obs-1" not in executor._tracker_context_by_observation
