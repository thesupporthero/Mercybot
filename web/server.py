from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import aiohttp.web

if TYPE_CHECKING:
    import asyncpg
    from bot import Mercybot

log = logging.getLogger(__name__)


async def start_web_server(bot: Mercybot, pool: asyncpg.Pool, *, host: str = 'localhost', port: int = 8080) -> aiohttp.web.AppRunner:
    """Start the web server and return the runner for cleanup."""
    from . import create_app

    app = create_app(bot, pool)
    runner = aiohttp.web.AppRunner(app)
    await runner.setup()

    site = aiohttp.web.TCPSite(runner, host, port)
    await site.start()

    log.info('Web server started on %s:%d', host, port)
    return runner


async def stop_web_server(runner: aiohttp.web.AppRunner) -> None:
    """Gracefully stop the web server."""
    log.info('Shutting down web server...')
    await runner.cleanup()
