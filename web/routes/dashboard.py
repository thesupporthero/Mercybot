from __future__ import annotations

import logging

import aiohttp.web
import aiohttp_jinja2
from aiohttp_session import get_session

from ..helpers import get_bot, require_guild_access, guild_icon_url, generate_csrf_token, validate_csrf_token

log = logging.getLogger(__name__)

routes = aiohttp.web.RouteTableDef()


def _guild_dict(guild, **extra) -> dict:
    """Build a standard guild context dict for templates."""
    d = {
        'id': guild.id,
        'name': guild.name,
        'icon_url': guild_icon_url(guild.id, guild.icon.key if guild.icon else None),
        'member_count': guild.member_count or 0,
    }
    d.update(extra)
    return d


@routes.get('/dashboard')
@aiohttp_jinja2.template('dashboard/guild_list.html')
async def guild_list(request: aiohttp.web.Request) -> dict:
    """List guilds the user can manage."""
    session = await get_session(request)
    guilds = session.get('guilds', [])

    # Add icon URLs
    for guild in guilds:
        guild['icon_url'] = guild_icon_url(guild['id'], guild.get('icon'))

    return {'guilds': guilds}


@routes.get('/dashboard/{guild_id}')
@aiohttp_jinja2.template('dashboard/guild_overview.html')
async def guild_overview(request: aiohttp.web.Request) -> dict:
    """Guild overview page with summary of all configs."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    # Fetch summary data in parallel
    mod_config = await pool.fetchrow('SELECT * FROM guild_mod_config WHERE id = $1', guild_id)
    ticket_stats = await pool.fetchrow(
        "SELECT COUNT(*) FILTER (WHERE status = 'open') AS open_tickets, "
        "COUNT(*) FILTER (WHERE status = 'closed') AS closed_tickets "
        "FROM tickets WHERE guild_id = $1",
        guild_id,
    )
    tag_count = await pool.fetchval('SELECT COUNT(*) FROM tags WHERE location_id = $1', guild_id)
    starboard = await pool.fetchrow('SELECT * FROM starboard WHERE id = $1', guild_id)

    return {
        'guild': _guild_dict(guild),
        'mod_config': dict(mod_config) if mod_config else None,
        'ticket_stats': dict(ticket_stats) if ticket_stats else {'open_tickets': 0, 'closed_tickets': 0},
        'tag_count': tag_count or 0,
        'starboard': dict(starboard) if starboard else None,
    }


@routes.get('/dashboard/{guild_id}/mod')
@aiohttp_jinja2.template('dashboard/mod_settings.html')
async def mod_settings(request: aiohttp.web.Request) -> dict:
    """View/edit moderation settings."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    config = await pool.fetchrow('SELECT * FROM guild_mod_config WHERE id = $1', guild_id)
    csrf_token = await generate_csrf_token(request)

    automod_flags = config['automod_flags'] or 0 if config else 0

    return {
        'guild': _guild_dict(
            guild,
            channels=[{'id': c.id, 'name': c.name} for c in guild.text_channels],
            roles=[{'id': r.id, 'name': r.name} for r in guild.roles if not r.is_default()],
        ),
        'config': dict(config) if config else {},
        'flags': {
            'joins': bool(automod_flags & 1),
            'raid': bool(automod_flags & 2),
            'alerts': bool(automod_flags & 4),
            'gatekeeper': bool(automod_flags & 8),
        },
        'csrf_token': csrf_token,
    }


@routes.post('/dashboard/{guild_id}/mod')
async def mod_settings_save(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Save moderation settings."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)
    await validate_csrf_token(request)

    bot = get_bot(request)
    pool = request.app['pool']

    data = await request.post()

    # Build automod flags
    automod_flags = 0
    if data.get('flag_joins'):
        automod_flags |= 1
    if data.get('flag_raid'):
        automod_flags |= 2
    if data.get('flag_alerts'):
        automod_flags |= 4
    if data.get('flag_gatekeeper'):
        automod_flags |= 8

    mention_count = int(data['mention_count']) if data.get('mention_count') else None
    broadcast_channel = int(data['broadcast_channel']) if data.get('broadcast_channel') else None
    mute_role_id = int(data['mute_role_id']) if data.get('mute_role_id') else None

    query = """
        INSERT INTO guild_mod_config (id, automod_flags, mention_count, broadcast_channel, mute_role_id)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET
            automod_flags = $2,
            mention_count = $3,
            broadcast_channel = $4,
            mute_role_id = $5
    """
    await pool.execute(query, guild_id, automod_flags, mention_count, broadcast_channel, mute_role_id)

    # Invalidate the bot's cache
    mod_cog = bot.get_cog('Mod')
    if mod_cog and hasattr(mod_cog, 'get_guild_config'):
        mod_cog.get_guild_config.invalidate(mod_cog, guild_id)

    raise aiohttp.web.HTTPFound(f'/dashboard/{guild_id}/mod?saved=1')


@routes.get('/dashboard/{guild_id}/tickets')
@aiohttp_jinja2.template('dashboard/tickets.html')
async def tickets_view(request: aiohttp.web.Request) -> dict:
    """View ticket configuration."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    config = await pool.fetchrow('SELECT * FROM ticket_config WHERE id = $1', guild_id)
    categories = await pool.fetch('SELECT * FROM ticket_categories WHERE guild_id = $1 ORDER BY name', guild_id)
    support_roles = await pool.fetch('SELECT role_id FROM ticket_support_roles WHERE guild_id = $1', guild_id)
    ticket_stats = await pool.fetchrow(
        "SELECT COUNT(*) FILTER (WHERE status = 'open') AS open_count, "
        "COUNT(*) FILTER (WHERE status = 'closed') AS closed_count "
        "FROM tickets WHERE guild_id = $1",
        guild_id,
    )

    # Resolve role names
    role_names = []
    for row in support_roles:
        role = guild.get_role(row['role_id'])
        role_names.append({'id': row['role_id'], 'name': role.name if role else 'Deleted Role'})

    # Resolve channel names
    panel_channel = guild.get_channel(config['channel_id']) if config and config['channel_id'] else None
    log_channel = guild.get_channel(config['log_channel_id']) if config and config['log_channel_id'] else None

    return {
        'guild': _guild_dict(guild),
        'config': dict(config) if config else None,
        'panel_channel': panel_channel.name if panel_channel else None,
        'log_channel': log_channel.name if log_channel else None,
        'categories': [dict(c) for c in categories],
        'support_roles': role_names,
        'stats': dict(ticket_stats) if ticket_stats else {'open_count': 0, 'closed_count': 0},
    }


@routes.get('/dashboard/{guild_id}/tags')
@aiohttp_jinja2.template('dashboard/tags.html')
async def tags_view(request: aiohttp.web.Request) -> dict:
    """Browse guild tags (read-only)."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    page = int(request.query.get('page', 1))
    per_page = 25
    offset = (page - 1) * per_page

    total = await pool.fetchval('SELECT COUNT(*) FROM tags WHERE location_id = $1', guild_id)
    tags = await pool.fetch(
        'SELECT id, name, owner_id, uses, created_at FROM tags WHERE location_id = $1 ORDER BY uses DESC LIMIT $2 OFFSET $3',
        guild_id, per_page, offset,
    )

    return {
        'guild': _guild_dict(guild),
        'tags': [dict(t) for t in tags],
        'page': page,
        'total': total or 0,
        'total_pages': max(1, (total or 0 + per_page - 1) // per_page),
    }


@routes.get('/dashboard/{guild_id}/starboard')
@aiohttp_jinja2.template('dashboard/starboard.html')
async def starboard_view(request: aiohttp.web.Request) -> dict:
    """View starboard configuration."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    config = await pool.fetchrow('SELECT * FROM starboard WHERE id = $1', guild_id)
    total_entries = await pool.fetchval('SELECT COUNT(*) FROM starboard_entries WHERE guild_id = $1', guild_id)

    # Resolve channel name
    star_channel = guild.get_channel(config['channel_id']) if config and config['channel_id'] else None

    return {
        'guild': _guild_dict(guild),
        'config': dict(config) if config else None,
        'star_channel': star_channel.name if star_channel else None,
        'total_entries': total_entries or 0,
    }


@routes.get('/dashboard/{guild_id}/stats')
@aiohttp_jinja2.template('dashboard/stats.html')
async def stats_view(request: aiohttp.web.Request) -> dict:
    """Guild command usage statistics."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    # Top commands for this guild
    top_commands = await pool.fetch(
        'SELECT command, COUNT(*) AS uses FROM commands WHERE guild_id = $1 GROUP BY command ORDER BY uses DESC LIMIT 15',
        guild_id,
    )

    # Total commands in last 24h
    recent_count = await pool.fetchval(
        "SELECT COUNT(*) FROM commands WHERE guild_id = $1 AND used > NOW() - INTERVAL '24 hours'",
        guild_id,
    )

    total_count = await pool.fetchval('SELECT COUNT(*) FROM commands WHERE guild_id = $1', guild_id)

    return {
        'guild': _guild_dict(guild),
        'top_commands': [dict(c) for c in top_commands],
        'recent_count': recent_count or 0,
        'total_count': total_count or 0,
    }
