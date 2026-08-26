# Copyright (c) 2026 Efstratios Goudelis

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handlers.entities import databasebackup


@pytest.mark.asyncio
async def test_full_restore_file_streams_sql_without_loading_the_complete_backup(
    monkeypatch, tmp_path
):
    """A disk-backed restore retains quoted semicolons and defers indexes until data is loaded."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    monkeypatch.setattr(databasebackup, "AsyncSessionLocal", session_factory)

    backup_file = tmp_path / "backup.sql"
    backup_file.write_text(
        """-- Full Database Backup
CREATE TABLE widgets (id INTEGER PRIMARY KEY, value TEXT);
CREATE INDEX widgets_value_idx ON widgets (value);
INSERT INTO widgets (id, value) VALUES (1, 'contains; a semicolon');
CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL);
INSERT INTO alembic_version (version_num) VALUES ('revision-1');
"""
    )

    try:
        restore_reply = await databasebackup.full_restore_file(backup_file)
        assert restore_reply["success"] is True
        assert restore_reply["tables_created"] == 2
        assert restore_reply["indexes_created"] == 1
        assert restore_reply["rows_inserted"] == 2

        async with session_factory() as session:
            value = (await session.execute(text("SELECT value FROM widgets"))).scalar_one()
            assert value == "contains; a semicolon"
    finally:
        await engine.dispose()
