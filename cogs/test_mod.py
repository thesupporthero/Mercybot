import types
from types import SimpleNamespace
from contextlib import asynccontextmanager
import pytest
from cogs import mod

@pytest.mark.asyncio
async def test_get_guild_config_returns_modconfig(monkeypatch):
    record = {"id": 111, "some": "data"}

    @asynccontextmanager
    async def acquire(timeout=None):
        class Conn:
            async def fetchrow(self, query, guild_id):
                assert guild_id == 111
                return record

        yield Conn()

    fake_pool = SimpleNamespace(acquire=acquire)
    fake_bot = SimpleNamespace(pool=fake_pool)

    # Replace ModConfig.from_record to verify it's called and return a sentinel
    sentinel = object()
    class DummyModConfig:
        @staticmethod
        def from_record(rec, bot):
            assert rec is record
            assert bot is fake_bot
            return sentinel

    original_modconfig = getattr(mod, "ModConfig", None)
    monkeypatch.setattr(mod, "ModConfig", DummyModConfig)

    try:
        inst = SimpleNamespace(bot=fake_bot)
        method = mod.Mod.get_guild_config.__get__(inst, mod.Mod)
        result = await method(111)
        assert result is sentinel
    finally:
        if original_modconfig is None:
            delattr(mod, "ModConfig")
        else:
            monkeypatch.setattr(mod, "ModConfig", original_modconfig)


@pytest.mark.asyncio
async def test_get_guild_config_returns_none_when_no_record(monkeypatch):
    @asynccontextmanager
    async def acquire(timeout=None):
        class Conn:
            async def fetchrow(self, query, guild_id):
                return None

        yield Conn()

    fake_pool = SimpleNamespace(acquire=acquire)
    fake_bot = SimpleNamespace(pool=fake_pool)

    inst = SimpleNamespace(bot=fake_bot)
    method = mod.Mod.get_guild_config.__get__(inst, mod.Mod)
    result = await method(222)
    assert result is None