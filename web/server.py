from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import aiohttp.web

if TYPE_CHECKING:
    import asyncpg
    from bot import Mercybot

log = logging.getLogger(__name__)

# Module-level reference so it survives across bot attribute resets
_runner: Optional[aiohttp.web.AppRunner] = None


async def start_web_server(bot: Mercybot, pool: asyncpg.Pool, *, host: str = 'localhost', port: int = 8080) -> aiohttp.web.AppRunner:
    """Start the web server and return the runner for cleanup."""
    global _runner
    from . import create_app

    app = create_app(bot, pool)
    _runner = aiohttp.web.AppRunner(app)
    await _runner.setup()

    site = aiohttp.web.TCPSite(_runner, host, port)
    await site.start()

    log.info('Web server started on %s:%d', host, port)
    return _runner


async def stop_web_server(runner: Optional[aiohttp.web.AppRunner] = None) -> None:
    """Gracefully stop the web server."""
    global _runner
    target = runner or _runner
    if target is None:
        return
    log.info('Shutting down web server...')
    await target.cleanup()
    _runner = None
