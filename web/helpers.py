from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

import aiohttp.web
import discord
from aiohttp_session import get_session

if TYPE_CHECKING:
    from bot import Mercybot

MANAGE_GUILD = 0x20  # discord.Permissions.manage_guild


def get_bot(request: aiohttp.web.Request) -> Mercybot:
    """Get the bot instance from the request."""
    return request.app['bot']


def get_member_guild_ids(bot: Mercybot, user_guilds: list[dict]) -> list[int]:
    """Return IDs of all guilds the user is in that the bot is also in."""
    bot_guild_ids = {g.id for g in bot.guilds}
    return [int(g['id']) for g in user_guilds if int(g['id']) in bot_guild_ids]


def get_member_only_guilds(bot: Mercybot, user_guilds: list[dict], manageable_ids: list[int]) -> list[dict]:
    """Return guild details for guilds the user is in but cannot manage."""
    bot_guild_ids = {g.id for g in bot.guilds}
    manageable_set = set(manageable_ids)
    result = []
    for guild in user_guilds:
        guild_id = int(guild['id'])
        if guild_id in bot_guild_ids and guild_id not in manageable_set:
            bot_guild = bot.get_guild(guild_id)
            result.append({
                'id': guild_id,
                'name': guild['name'],
                'icon': guild.get('icon'),
                'member_count': bot_guild.member_count if bot_guild else 0,
            })
    return result


def get_manageable_guilds(bot: Mercybot, user_guilds: list[dict]) -> list[dict]:
    """Return guilds the user can manage that the bot is also in."""
    bot_guild_ids = {g.id for g in bot.guilds}
    result = []

    for guild in user_guilds:
        guild_id = int(guild['id'])
        permissions = int(guild.get('permissions', 0))
        is_owner = guild.get('owner', False)

        if guild_id not in bot_guild_ids:
            continue

        if is_owner or (permissions & MANAGE_GUILD):
            bot_guild = bot.get_guild(guild_id)
            result.append({
                'id': guild_id,
                'name': guild['name'],
                'icon': guild.get('icon'),
                'member_count': bot_guild.member_count if bot_guild else 0,
            })

    return result


def guild_icon_url(guild_id: int, icon_hash: str | None, size: int = 128) -> str:
    """Get a guild's icon URL or a default."""
    if icon_hash:
        fmt = 'gif' if icon_hash.startswith('a_') else 'png'
        return f'https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.{fmt}?size={size}'
    return f'https://cdn.discordapp.com/embed/avatars/{guild_id % 5}.png'


def user_avatar_url(user_id: int, avatar_hash: str | None, discriminator: str = '0', size: int = 128) -> str:
    """Get a user's avatar URL or a default."""
    if avatar_hash:
        fmt = 'gif' if avatar_hash.startswith('a_') else 'png'
        return f'https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{fmt}?size={size}'
    index = (user_id >> 22) % 6
    return f'https://cdn.discordapp.com/embed/avatars/{index}.png'


async def require_guild_member(request: aiohttp.web.Request, guild_id: int) -> None:
    """Raise 403 if the user is not a member of this guild (bot must also be in it)."""
    bot = get_bot(request)

    if request['user']['id'] == bot.owner_id:
        return

    if guild_id not in request['member_guild_ids']:
        raise aiohttp.web.HTTPForbidden(text='You are not a member of this guild.')


async def require_guild_access(request: aiohttp.web.Request, guild_id: int) -> None:
    """Raise 403 if the user cannot manage this guild."""
    bot = get_bot(request)

    # Bot owner always has access
    if request['user']['id'] == bot.owner_id:
        return

    if guild_id not in request['guild_ids']:
        raise aiohttp.web.HTTPForbidden(text='You do not have permission to manage this guild.')


async def generate_csrf_token(request: aiohttp.web.Request) -> str:
    """Generate or retrieve a CSRF token for the session."""
    session = await get_session(request)
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


async def validate_csrf_token(request: aiohttp.web.Request) -> None:
    """Validate the CSRF token from a POST request."""
    session = await get_session(request)
    expected = session.get('csrf_token')

    data = await request.post()
    token = data.get('csrf_token')

    if not expected or not token or token != expected:
        raise aiohttp.web.HTTPForbidden(text='Invalid CSRF token.')
