from __future__ import annotations

import logging
import math

import aiohttp.web
import aiohttp_jinja2
from aiohttp_session import get_session

from ..helpers import get_bot, require_guild_access, require_guild_member, guild_icon_url, generate_csrf_token, validate_csrf_token

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
    """List guilds the user can manage, plus member-only guilds with leaderboard access."""
    session = await get_session(request)
    guilds = session.get('guilds', [])
    member_only_guilds = session.get('member_only_guilds', [])

    for guild in guilds:
        guild['icon_url'] = guild_icon_url(guild['id'], guild.get('icon'))
    for guild in member_only_guilds:
        guild['icon_url'] = guild_icon_url(guild['id'], guild.get('icon'))

    return {'guilds': guilds, 'member_only_guilds': member_only_guilds}


@routes.get('/dashboard/leaderboard')
@aiohttp_jinja2.template('dashboard/leaderboard_list.html')
async def leaderboard_list(request: aiohttp.web.Request) -> dict:
    """List all servers the user is in for leaderboard access."""
    session = await get_session(request)
    guilds = list(session.get('guilds', []))
    member_only_guilds = list(session.get('member_only_guilds', []))

    # Combine both lists — any server the user is in can show a leaderboard
    all_guilds = guilds + member_only_guilds
    for guild in all_guilds:
        guild['icon_url'] = guild_icon_url(guild['id'], guild.get('icon'))

    return {'guilds': all_guilds}


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

    # Decode automod flags into human-readable labels
    automod_labels = []
    if mod_config:
        flags = mod_config['automod_flags'] or 0
        if flags & 1:
            automod_labels.append('Joins')
        if flags & 2:
            automod_labels.append('Raid')
        if flags & 4:
            automod_labels.append('Alerts')
        if flags & 8:
            automod_labels.append('Gatekeeper')

    # Resolve starboard channel name
    star_channel = None
    if starboard and starboard['channel_id']:
        ch = guild.get_channel(starboard['channel_id'])
        star_channel = ch.name if ch else None

    return {
        'guild': _guild_dict(guild),
        'mod_config': dict(mod_config) if mod_config else None,
        'automod_labels': automod_labels,
        'ticket_stats': dict(ticket_stats) if ticket_stats else {'open_tickets': 0, 'closed_tickets': 0},
        'tag_count': tag_count or 0,
        'starboard': dict(starboard) if starboard else None,
        'star_channel': star_channel,
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
    """View/edit ticket configuration."""
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
    support_role_ids = set()
    for row in support_roles:
        role = guild.get_role(row['role_id'])
        role_names.append({'id': row['role_id'], 'name': role.name if role else 'Deleted Role'})
        support_role_ids.add(row['role_id'])

    csrf_token = await generate_csrf_token(request)

    return {
        'guild': _guild_dict(
            guild,
            channels=[{'id': c.id, 'name': c.name} for c in guild.text_channels],
            category_channels=[{'id': c.id, 'name': c.name} for c in guild.categories],
            roles=[{'id': r.id, 'name': r.name} for r in guild.roles if not r.is_default()],
        ),
        'config': dict(config) if config else None,
        'categories': [dict(c) for c in categories],
        'support_roles': role_names,
        'support_role_ids': support_role_ids,
        'stats': dict(ticket_stats) if ticket_stats else {'open_count': 0, 'closed_count': 0},
        'csrf_token': csrf_token,
    }


@routes.post('/dashboard/{guild_id}/tickets')
async def tickets_save(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Save ticket configuration."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)
    await validate_csrf_token(request)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    data = await request.post()

    channel_id = int(data['channel_id']) if data.get('channel_id') else None
    category_id = int(data['category_id']) if data.get('category_id') else None
    log_channel_id = int(data['log_channel_id']) if data.get('log_channel_id') else None
    ping_roles = bool(data.get('ping_roles'))
    auto_delete = bool(data.get('auto_delete'))

    # Upsert config
    query = """
        INSERT INTO ticket_config (id, channel_id, log_channel_id, category_id, ping_roles, auto_delete)
        VALUES ($1, $2, $3, $4, $5, $6)
        ON CONFLICT (id) DO UPDATE SET
            channel_id = EXCLUDED.channel_id,
            log_channel_id = EXCLUDED.log_channel_id,
            category_id = EXCLUDED.category_id,
            ping_roles = EXCLUDED.ping_roles,
            auto_delete = EXCLUDED.auto_delete;
    """
    await pool.execute(query, guild_id, channel_id, log_channel_id, category_id, ping_roles, auto_delete)

    # Parse categories from form (cat_name_0, cat_desc_0, cat_name_1, ...)
    await pool.execute("DELETE FROM ticket_categories WHERE guild_id=$1;", guild_id)
    i = 0
    while True:
        name = data.get(f'cat_name_{i}')
        if name is None:
            break
        name = name.strip()
        if name:
            desc = (data.get(f'cat_desc_{i}') or '').strip() or None
            await pool.execute(
                "INSERT INTO ticket_categories (guild_id, name, description) VALUES ($1, $2, $3);",
                guild_id, name, desc,
            )
        i += 1

    # Parse support roles from form (multi-select checkboxes)
    await pool.execute("DELETE FROM ticket_support_roles WHERE guild_id=$1;", guild_id)
    role_ids = data.getall('support_roles', [])
    for role_id in role_ids:
        await pool.execute(
            "INSERT INTO ticket_support_roles (guild_id, role_id) VALUES ($1, $2);",
            guild_id, int(role_id),
        )

    # Re-post panel if panel channel is set
    if channel_id:
        ticket_cog = bot.get_cog('Tickets')
        panel_channel = guild.get_channel(channel_id)
        if ticket_cog and panel_channel:
            try:
                await ticket_cog.post_panel(panel_channel, guild_id)
            except Exception:
                log.warning('Failed to re-post ticket panel for guild %d', guild_id, exc_info=True)

    raise aiohttp.web.HTTPFound(f'/dashboard/{guild_id}/tickets?saved=1')


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
    csrf_token = await generate_csrf_token(request)

    return {
        'guild': _guild_dict(
            guild,
            channels=[{'id': c.id, 'name': c.name} for c in guild.text_channels],
        ),
        'config': dict(config) if config else None,
        'star_channel': star_channel.name if star_channel else None,
        'total_entries': total_entries or 0,
        'csrf_token': csrf_token,
    }


@routes.post('/dashboard/{guild_id}/starboard')
async def starboard_save(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Save starboard settings."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)
    await validate_csrf_token(request)

    bot = get_bot(request)
    pool = request.app['pool']

    # Check if starboard exists
    existing = await pool.fetchrow('SELECT * FROM starboard WHERE id = $1', guild_id)
    if not existing:
        raise aiohttp.web.HTTPBadRequest(text='Starboard is not set up. Use the bot command to create it first.')

    data = await request.post()

    channel_id = int(data['channel_id']) if data.get('channel_id') else existing['channel_id']
    threshold = min(max(int(data.get('threshold', 1)), 1), 100)
    locked = bool(data.get('locked'))

    # Handle max_age
    max_age_days = data.get('max_age_days')
    if max_age_days and max_age_days.strip():
        days = min(max(int(max_age_days), 1), 3650)
        max_age_sql = f"'{days} days'::interval"
    else:
        max_age_sql = 'NULL'

    query = f"""
        UPDATE starboard
        SET channel_id = $2, threshold = $3, locked = $4, max_age = {max_age_sql}
        WHERE id = $1
    """
    await pool.execute(query, guild_id, channel_id, threshold, locked)

    # Invalidate the bot's starboard cache
    stars_cog = bot.get_cog('Stars')
    if stars_cog and hasattr(stars_cog, 'get_starboard'):
        stars_cog.get_starboard.invalidate(stars_cog, guild_id)

    raise aiohttp.web.HTTPFound(f'/dashboard/{guild_id}/starboard?saved=1')


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


# -- Levels (XP config) --

@routes.get('/dashboard/{guild_id}/levels')
@aiohttp_jinja2.template('dashboard/levels.html')
async def levels_view(request: aiohttp.web.Request) -> dict:
    """View/edit XP and leveling configuration."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    config = await pool.fetchrow('SELECT * FROM xp_config WHERE guild_id = $1', guild_id)
    csrf_token = await generate_csrf_token(request)

    return {
        'guild': _guild_dict(guild),
        'config': dict(config) if config else None,
        'csrf_token': csrf_token,
    }


@routes.post('/dashboard/{guild_id}/levels')
async def levels_save(request: aiohttp.web.Request) -> aiohttp.web.Response:
    """Save XP and leveling configuration."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_access(request, guild_id)
    await validate_csrf_token(request)

    bot = get_bot(request)
    pool = request.app['pool']

    data = await request.post()

    enabled = bool(data.get('enabled'))
    xp_min = min(max(int(data.get('xp_min', 15)), 1), 100)
    xp_max = min(max(int(data.get('xp_max', 25)), 1), 100)
    cooldown = min(max(int(data.get('cooldown', 60)), 10), 300)
    voice_xp_rate = min(max(int(data.get('voice_xp_rate', 5)), 1), 50)
    level_formula = int(data.get('level_formula', 50))

    # Ensure xp_min <= xp_max
    if xp_min > xp_max:
        xp_min, xp_max = xp_max, xp_min

    # Clamp level_formula to allowed presets
    if level_formula not in (15, 30, 50, 80):
        level_formula = 50

    query = """
        INSERT INTO xp_config (guild_id, enabled, xp_min, xp_max, cooldown, voice_xp_rate, level_formula)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (guild_id) DO UPDATE SET
            enabled = EXCLUDED.enabled,
            xp_min = EXCLUDED.xp_min,
            xp_max = EXCLUDED.xp_max,
            cooldown = EXCLUDED.cooldown,
            voice_xp_rate = EXCLUDED.voice_xp_rate,
            level_formula = EXCLUDED.level_formula;
    """
    await pool.execute(query, guild_id, enabled, xp_min, xp_max, cooldown, voice_xp_rate, level_formula)

    # Invalidate the cog's in-memory cache
    profile_cog = bot.get_cog('Profile')
    if profile_cog and hasattr(profile_cog, 'invalidate_config'):
        profile_cog.invalidate_config(guild_id)

    raise aiohttp.web.HTTPFound(f'/dashboard/{guild_id}/levels?saved=1')


# -- Leaderboard --

def _get_level(xp: int, base: int = 50) -> int:
    if xp <= 0 or base <= 0:
        return 0
    return int(math.sqrt(xp / base))


def _format_voice_time(minutes: int) -> str:
    if minutes < 60:
        return f'{minutes}m'
    hours, mins = divmod(minutes, 60)
    return f'{hours}h {mins}m'


@routes.get('/dashboard/{guild_id}/leaderboard')
@aiohttp_jinja2.template('dashboard/leaderboard.html')
async def leaderboard_view(request: aiohttp.web.Request) -> dict:
    """View server XP leaderboard."""
    guild_id = int(request.match_info['guild_id'])
    await require_guild_member(request, guild_id)

    bot = get_bot(request)
    pool = request.app['pool']
    guild = bot.get_guild(guild_id)

    if not guild:
        raise aiohttp.web.HTTPNotFound(text='Guild not found.')

    # Get XP config for level formula
    xp_config = await pool.fetchrow('SELECT level_formula FROM xp_config WHERE guild_id = $1', guild_id)
    base = xp_config['level_formula'] if xp_config else 50

    page = max(1, int(request.query.get('page', 1)))
    per_page = 25
    offset = (page - 1) * per_page

    total = await pool.fetchval('SELECT COUNT(*) FROM guild_profiles WHERE guild_id = $1', guild_id)
    rows = await pool.fetch(
        'SELECT user_id, xp, message_count, voice_minutes FROM guild_profiles WHERE guild_id = $1 ORDER BY xp DESC LIMIT $2 OFFSET $3',
        guild_id, per_page, offset,
    )

    # Resolve member names: guild cache -> global user cache -> fetch from Discord
    entries = []
    for i, row in enumerate(rows):
        user_id = row['user_id']
        member = guild.get_member(user_id)
        if member:
            name = member.display_name
        else:
            user = bot.get_user(user_id)
            if user is None:
                try:
                    user = await bot.fetch_user(user_id)
                except Exception:
                    user = None
            name = str(user) if user else f'Unknown ({user_id})'
        entries.append({
            'rank': offset + i + 1,
            'user_id': user_id,
            'name': name,
            'level': _get_level(row['xp'], base),
            'xp': row['xp'],
            'message_count': row['message_count'],
            'voice_time': _format_voice_time(row['voice_minutes']),
        })

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1

    is_manager = guild_id in request['guild_ids']

    return {
        'guild': _guild_dict(guild),
        'entries': entries,
        'page': page,
        'total': total or 0,
        'total_pages': total_pages,
        'is_manager': is_manager,
    }
