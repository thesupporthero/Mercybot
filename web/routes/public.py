from __future__ import annotations

import discord
import aiohttp.web
import aiohttp_jinja2

from ..helpers import get_bot

routes = aiohttp.web.RouteTableDef()


@routes.get('/')
@aiohttp_jinja2.template('public/index.html')
async def index(request: aiohttp.web.Request) -> dict:
    """Public landing page with bot stats."""
    bot = get_bot(request)
    stats = _gather_stats(bot)
    return {'stats': stats}


@routes.get('/api/stats')
async def api_stats(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """JSON endpoint for live stats (auto-refresh)."""
    bot = get_bot(request)
    stats = _gather_stats(bot)
    return aiohttp.web.json_response(stats)


def _gather_stats(bot) -> dict:
    """Gather bot statistics from the live bot object."""
    total_members = 0
    total_unique = len(bot.users)
    text_channels = 0
    voice_channels = 0
    guild_count = 0

    for guild in bot.guilds:
        guild_count += 1
        if guild.unavailable:
            continue
        total_members += guild.member_count or 0
        for channel in guild.channels:
            if isinstance(channel, discord.TextChannel):
                text_channels += 1
            elif isinstance(channel, discord.VoiceChannel):
                voice_channels += 1

    # Top commands
    top_commands = []
    if hasattr(bot, 'command_stats'):
        for name, count in bot.command_stats.most_common(10):
            top_commands.append({'name': name, 'count': count})

    # Uptime
    uptime_seconds = 0
    if hasattr(bot, 'uptime'):
        delta = discord.utils.utcnow() - bot.uptime
        uptime_seconds = int(delta.total_seconds())

    return {
        'guild_count': guild_count,
        'total_members': total_members,
        'unique_users': total_unique,
        'text_channels': text_channels,
        'voice_channels': voice_channels,
        'latency_ms': round(bot.latency * 1000, 1),
        'uptime_seconds': uptime_seconds,
        'top_commands': top_commands,
        'commands_run': sum(bot.command_stats.values()) if hasattr(bot, 'command_stats') else 0,
    }
