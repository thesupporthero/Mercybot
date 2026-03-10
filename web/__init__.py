from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp.web
import aiohttp_jinja2
import jinja2
from aiohttp_session import setup as setup_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography.fernet import Fernet

from .middleware import error_middleware, auth_middleware
from .routes import setup_routes

if TYPE_CHECKING:
    import asyncpg
    from bot import Mercybot

BASE_DIR = Path(__file__).parent


def format_number(value: int) -> str:
    """Format large numbers with commas."""
    return f'{value:,}'


def format_uptime(seconds: int) -> str:
    """Format seconds into a human-readable uptime string."""
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)
    if days:
        return f'{days}d {hours}h'
    if hours:
        return f'{hours}h {minutes}m'
    return f'{minutes}m'


def create_app(bot: Mercybot, pool: asyncpg.Pool) -> aiohttp.web.Application:
    """Create and configure the aiohttp web application."""
    app = aiohttp.web.Application(middlewares=[error_middleware, auth_middleware])

    # Store bot and pool references
    app['bot'] = bot
    app['pool'] = pool

    # Set up Jinja2 templates
    env = aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(BASE_DIR / 'templates')),
        context_processors=[default_context],
    )

    # Register custom filters
    env.filters['format_number'] = format_number
    env.filters['format_uptime'] = format_uptime

    # Set up encrypted cookie sessions
    secret_key = bot.config.dashboard_secret_key
    if isinstance(secret_key, str):
        secret_key = secret_key.encode()

    # Fernet key must be 32 url-safe base64-encoded bytes
    setup_session(app, EncryptedCookieStorage(secret_key, cookie_name='mercybot_session', max_age=3600))

    # Set up static file serving
    app.router.add_static('/static', str(BASE_DIR / 'static'), name='static')

    # Register routes
    setup_routes(app)

    return app


async def default_context(request: aiohttp.web.Request) -> dict:
    """Default template context available in all templates."""
    from aiohttp_session import get_session
    session = await get_session(request)

    return {
        'user': session.get('user'),
        'bot_name': 'Mercybot',
    }
