from __future__ import annotations

import secrets
import logging

import aiohttp
import aiohttp.web
from aiohttp_session import get_session

from ..helpers import get_bot, get_manageable_guilds, user_avatar_url

log = logging.getLogger(__name__)

routes = aiohttp.web.RouteTableDef()

DISCORD_API = 'https://discord.com/api/v10'
DISCORD_OAUTH2_URL = 'https://discord.com/oauth2/authorize'
DISCORD_TOKEN_URL = f'{DISCORD_API}/oauth2/token'


def _get_redirect_uri(request: aiohttp.web.Request) -> str:
    bot = get_bot(request)
    base = getattr(bot.config, 'dashboard_url', 'http://localhost:8080')
    return f'{base}/auth/callback'


@routes.get('/auth/login')
async def login(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Redirect to Discord OAuth2 authorization."""
    bot = get_bot(request)
    session = await get_session(request)

    state = secrets.token_hex(16)
    session['oauth_state'] = state

    redirect_uri = _get_redirect_uri(request)

    url = (
        f'{DISCORD_OAUTH2_URL}'
        f'?client_id={bot.client_id}'
        f'&redirect_uri={redirect_uri}'
        f'&response_type=code'
        f'&scope=identify%20guilds'
        f'&state={state}'
    )

    raise aiohttp.web.HTTPFound(url)


@routes.get('/auth/callback')
async def callback(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Handle Discord OAuth2 callback."""
    bot = get_bot(request)
    session = await get_session(request)

    # Validate state
    state = request.query.get('state')
    expected_state = session.pop('oauth_state', None)
    if not state or state != expected_state:
        raise aiohttp.web.HTTPBadRequest(text='Invalid state parameter.')

    code = request.query.get('code')
    if not code:
        raise aiohttp.web.HTTPBadRequest(text='Missing authorization code.')

    error = request.query.get('error')
    if error:
        log.warning('OAuth2 error: %s - %s', error, request.query.get('error_description'))
        raise aiohttp.web.HTTPFound('/')

    redirect_uri = _get_redirect_uri(request)

    # Exchange code for access token
    token_data = {
        'client_id': bot.client_id,
        'client_secret': bot.config.client_secret,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
    }

    async with bot.session.post(DISCORD_TOKEN_URL, data=token_data, headers={'Content-Type': 'application/x-www-form-urlencoded'}) as resp:
        if resp.status != 200:
            log.error('Token exchange failed with status %d', resp.status)
            raise aiohttp.web.HTTPBadRequest(text='Failed to exchange authorization code.')
        tokens = await resp.json()

    access_token = tokens['access_token']
    headers = {'Authorization': f'Bearer {access_token}'}

    # Fetch user info
    async with bot.session.get(f'{DISCORD_API}/users/@me', headers=headers) as resp:
        if resp.status != 200:
            raise aiohttp.web.HTTPBadRequest(text='Failed to fetch user info.')
        user_data = await resp.json()

    # Fetch user guilds
    async with bot.session.get(f'{DISCORD_API}/users/@me/guilds', headers=headers) as resp:
        if resp.status != 200:
            raise aiohttp.web.HTTPBadRequest(text='Failed to fetch guild list.')
        user_guilds = await resp.json()

    # Determine manageable guilds
    manageable = get_manageable_guilds(bot, user_guilds)
    manageable_ids = [g['id'] for g in manageable]

    # Store in session
    user_id = int(user_data['id'])
    session['user'] = {
        'id': user_id,
        'username': user_data.get('global_name') or user_data['username'],
        'avatar_url': user_avatar_url(user_id, user_data.get('avatar'), user_data.get('discriminator', '0')),
    }
    session['guild_ids'] = manageable_ids
    session['guilds'] = manageable

    log.info('User %s (ID: %d) logged in via OAuth2', session['user']['username'], user_id)

    raise aiohttp.web.HTTPFound('/dashboard')


@routes.get('/auth/logout')
async def logout(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Clear session and redirect to home."""
    session = await get_session(request)
    session.clear()
    raise aiohttp.web.HTTPFound('/')
