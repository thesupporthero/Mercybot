from __future__ import annotations

import logging

import aiohttp.web
import aiohttp_jinja2
from aiohttp_session import get_session

log = logging.getLogger(__name__)

# Routes that require authentication
DASHBOARD_PREFIX = '/dashboard'


@aiohttp.web.middleware
async def error_middleware(request: aiohttp.web.Request, handler) -> aiohttp.web.StreamResponse:
    """Handle HTTP errors with proper error pages."""
    try:
        return await handler(request)
    except aiohttp.web.HTTPException:
        raise
    except Exception:
        log.exception('Unhandled error on %s %s', request.method, request.path)
        raise aiohttp.web.HTTPInternalServerError(text='Internal Server Error')


@aiohttp.web.middleware
async def auth_middleware(request: aiohttp.web.Request, handler) -> aiohttp.web.StreamResponse:
    """Check authentication for dashboard routes."""
    if not request.path.startswith(DASHBOARD_PREFIX):
        return await handler(request)

    session = await get_session(request)
    user = session.get('user')

    if not user:
        raise aiohttp.web.HTTPFound('/auth/login')

    request['user'] = user
    request['guild_ids'] = session.get('guild_ids', [])

    return await handler(request)
