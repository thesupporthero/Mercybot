from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import logging

import aiohttp.web
import aiohttp_jinja2
import jinja2
from aiohttp_session import setup as setup_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography.fernet import Fernet

log = logging.getLogger(__name__)

from .middleware import error_middleware, auth_middleware
from .routes import setup_routes

if TYPE_CHECKING:
    import asyncpg
    from bot import Mercybot

BASE_DIR = Path(__file__).parent


def format_number(value) -> str:
    """Format large numbers with commas."""
    if value is None or not isinstance(value, (int, float)):
        return '0'
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
    # Only error_middleware at creation — auth_middleware is added later
    # because it needs the session middleware to have run first.
    app = aiohttp.web.Application(middlewares=[error_middleware])

    # Store bot and pool references
    app['bot'] = bot
    app['pool'] = pool

    # 1. Session middleware (must be first — auth and jinja2 context processors need it)
    secret_key = getattr(bot.config, 'dashboard_secret_key', None)
    if not secret_key:
        log.warning('dashboard_secret_key not set in config.py — generating a temporary key. Sessions will not persist across restarts.')
        secret_key = Fernet.generate_key().decode()
    if isinstance(secret_key, bytes):
        secret_key = secret_key.decode()

    try:
        Fernet(secret_key)
    except Exception:
        raise ValueError(
            'dashboard_secret_key in config.py is invalid. '
            'Generate one with: python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        )

    setup_session(app, EncryptedCookieStorage(secret_key, cookie_name='mercybot_session', max_age=3600))

    # 2. Jinja2 templates (context processors need session access)
    env = aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(BASE_DIR / 'templates')),
        context_processors=[aiohttp_jinja2.request_processor, default_context],
    )

    env.filters['format_number'] = format_number
    env.filters['format_uptime'] = format_uptime

    # 3. Auth middleware LAST (needs session to be initialized first)
    app.middlewares.append(auth_middleware)

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
