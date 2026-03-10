from __future__ import annotations

import asyncio
import logging
import math
import random
import re
from collections import defaultdict
from typing import TYPE_CHECKING, Optional, Union

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands, menus, tasks
from typing_extensions import Annotated

from .utils.formats import plural
from .utils.paginator import SimplePages

if TYPE_CHECKING:
    from bot import Mercybot
    from .utils.context import Context

log = logging.getLogger(__name__)

# -- XP / Level helpers --

DEFAULT_XP_MIN = 15
DEFAULT_XP_MAX = 25
DEFAULT_COOLDOWN = 60
DEFAULT_VOICE_XP_RATE = 5
DEFAULT_LEVEL_BASE = 50


def get_level(xp: int, base: int = DEFAULT_LEVEL_BASE) -> int:
    if xp <= 0 or base <= 0:
        return 0
    return int(math.sqrt(xp / base))


def xp_for_level(level: int, base: int = DEFAULT_LEVEL_BASE) -> int:
    return level * level * base


def xp_to_next_level(xp: int, base: int = DEFAULT_LEVEL_BASE) -> tuple[int, int, int]:
    """Returns (current_level, xp_into_current, xp_needed_for_next)."""
    level = get_level(xp, base)
    current_level_xp = xp_for_level(level, base)
    next_level_xp = xp_for_level(level + 1, base)
    return level, xp - current_level_xp, next_level_xp - current_level_xp


def format_voice_time(minutes: int) -> str:
    if minutes < 60:
        return f'{minutes}m'
    hours, mins = divmod(minutes, 60)
    return f'{hours}h {mins}m'


# -- Member resolver (preserved from original) --

class DisambiguateMember(commands.IDConverter, app_commands.Transformer):
    async def convert(self, ctx: Context, argument: str) -> discord.abc.User:
        match = self._get_id_match(argument) or re.match(r'<@!?([0-9]+)>$', argument)

        if match is not None:
            user_id = int(match.group(1))
            result = ctx.bot.get_user(user_id)
            if result is None:
                try:
                    result = await ctx.bot.fetch_user(user_id)
                except discord.HTTPException:
                    raise commands.BadArgument("Could not find this member.") from None
            return result

        if len(argument) > 5 and argument[-5] == '#':
            name, _, discriminator = argument.rpartition('#')
            pred = lambda u: u.name == name and u.discriminator == discriminator
            result = discord.utils.find(pred, ctx.bot.users)
        else:
            matches: list[discord.Member | discord.User]
            if ctx.guild is None:
                matches = [user for user in ctx.bot.users if user.name == argument]
                entry = str
            else:
                matches = [
                    member
                    for member in ctx.guild.members
                    if member.name == argument or (member.nick and member.nick == argument)
                ]

                def to_str(m):
                    if m.nick:
                        return f'{m} (a.k.a {m.nick})'
                    else:
                        return str(m)

                entry = to_str

            try:
                result = await ctx.disambiguate(matches, entry)
            except Exception as e:
                raise commands.BadArgument(f'Could not find this member. {e}') from None

        if result is None:
            raise commands.BadArgument("Could not find this member. Note this is case sensitive.")
        return result

    @property
    def type(self) -> discord.AppCommandOptionType:
        return discord.AppCommandOptionType.user

    async def transform(self, interaction: discord.Interaction, value: discord.abc.User) -> discord.abc.User:
        return value


# -- Cog --

class Profile(commands.Cog):
    """Server profiles with XP, levels, and leaderboards."""

    def __init__(self, bot: Mercybot):
        self.bot: Mercybot = bot

        # Batch XP system (mirrors stats.py pattern)
        self._xp_batch_lock = asyncio.Lock()
        self._xp_batch: list[dict] = []

        # Message XP cooldowns: (guild_id, user_id) -> last_xp_timestamp
        self._xp_cooldowns: dict[tuple[int, int], float] = {}

        # Voice tracking: (guild_id, user_id) -> join_timestamp (utc)
        self._voice_join_times: dict[tuple[int, int], float] = {}

        # Per-guild XP config cache: guild_id -> config dict (or None for defaults)
        self._xp_configs: dict[int, Optional[dict]] = {}

        self.bulk_xp_loop.add_exception_type(asyncpg.PostgresConnectionError)
        self.bulk_xp_loop.start()
        self.voice_xp_sweep.start()
        self.config_refresh_loop.start()

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='\N{BUST IN SILHOUETTE}')

    def cog_unload(self):
        self.bulk_xp_loop.stop()
        self.voice_xp_sweep.stop()
        self.config_refresh_loop.stop()

    async def cog_load(self) -> None:
        # Populate voice tracking for members already in VC
        await self.bot.wait_until_ready()
        now = discord.utils.utcnow().timestamp()
        for guild in self.bot.guilds:
            for vs in guild.voice_states.values():
                member = guild.get_member(vs)
                if member and not member.bot:
                    state = member.voice
                    if state and self._is_voice_active(state):
                        self._voice_join_times[(guild.id, member.id)] = now

    # -- XP config helpers --

    def _get_config(self, guild_id: int) -> dict:
        """Get XP config for a guild, falling back to defaults."""
        cfg = self._xp_configs.get(guild_id)
        if cfg is not None:
            return cfg
        return {
            'enabled': True,
            'xp_min': DEFAULT_XP_MIN,
            'xp_max': DEFAULT_XP_MAX,
            'cooldown': DEFAULT_COOLDOWN,
            'voice_xp_rate': DEFAULT_VOICE_XP_RATE,
            'level_formula': DEFAULT_LEVEL_BASE,
        }

    async def _fetch_config(self, guild_id: int) -> Optional[dict]:
        row = await self.bot.pool.fetchrow('SELECT * FROM xp_config WHERE guild_id = $1', guild_id)
        return dict(row) if row else None

    def invalidate_config(self, guild_id: int) -> None:
        """Called by the dashboard after saving XP settings."""
        self._xp_configs.pop(guild_id, None)

    @tasks.loop(minutes=5.0)
    async def config_refresh_loop(self):
        """Periodically refresh all cached configs."""
        self._xp_configs.clear()
        rows = await self.bot.pool.fetch('SELECT * FROM xp_config')
        for row in rows:
            self._xp_configs[row['guild_id']] = dict(row)

    @config_refresh_loop.before_loop
    async def before_config_refresh(self):
        await self.bot.wait_until_ready()

    # -- Batch XP system --

    async def _bulk_xp_insert(self) -> None:
        if not self._xp_batch:
            return

        # Pre-aggregate: combine entries for the same (guild, user)
        aggregated: dict[tuple[int, int], dict] = {}
        for entry in self._xp_batch:
            key = (entry['guild'], entry['user'])
            if key in aggregated:
                agg = aggregated[key]
                agg['xp'] += entry['xp']
                agg['message_count'] += entry['message_count']
                agg['longest_message'] = max(agg['longest_message'], entry['longest_message'])
                agg['voice_minutes'] += entry['voice_minutes']
            else:
                aggregated[key] = entry.copy()

        batch = list(aggregated.values())

        query = """
            INSERT INTO guild_profiles (guild_id, user_id, xp, message_count, longest_message, voice_minutes)
            SELECT x.guild, x."user", x.xp, x.message_count, x.longest_message, x.voice_minutes
            FROM jsonb_to_recordset($1::jsonb) AS
            x(
                guild BIGINT,
                "user" BIGINT,
                xp BIGINT,
                message_count INTEGER,
                longest_message INTEGER,
                voice_minutes INTEGER
            )
            ON CONFLICT (guild_id, user_id) DO UPDATE SET
                xp = guild_profiles.xp + EXCLUDED.xp,
                message_count = guild_profiles.message_count + EXCLUDED.message_count,
                longest_message = GREATEST(guild_profiles.longest_message, EXCLUDED.longest_message),
                voice_minutes = guild_profiles.voice_minutes + EXCLUDED.voice_minutes;
        """

        await self.bot.pool.execute(query, batch)
        self._xp_batch.clear()

    @tasks.loop(seconds=15.0)
    async def bulk_xp_loop(self):
        async with self._xp_batch_lock:
            await self._bulk_xp_insert()
            # Prune stale cooldowns (older than 2x cooldown)
            now = discord.utils.utcnow().timestamp()
            stale = [k for k, v in self._xp_cooldowns.items() if now - v > 120]
            for k in stale:
                del self._xp_cooldowns[k]

    @bulk_xp_loop.before_loop
    async def before_bulk_xp(self):
        await self.bot.wait_until_ready()

    # -- Voice XP --

    def _is_voice_active(self, state: discord.VoiceState) -> bool:
        if state.channel is None:
            return False
        if state.channel == state.channel.guild.afk_channel:
            return False
        if state.deaf or state.mute:  # server deaf/mute only
            return False
        return True

    def _award_voice_xp(self, guild_id: int, user_id: int, join_timestamp: float) -> None:
        cfg = self._get_config(guild_id)
        if not cfg['enabled']:
            return
        now = discord.utils.utcnow().timestamp()
        minutes = int((now - join_timestamp) / 60.0)
        if minutes <= 0:
            return
        xp = minutes * cfg['voice_xp_rate']
        self._xp_batch.append({
            'guild': guild_id,
            'user': user_id,
            'xp': xp,
            'message_count': 0,
            'longest_message': 0,
            'voice_minutes': minutes,
        })

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if member.bot:
            return

        key = (member.guild.id, member.id)
        was_active = self._is_voice_active(before)
        is_active = self._is_voice_active(after)

        if not was_active and is_active:
            self._voice_join_times[key] = discord.utils.utcnow().timestamp()
        elif was_active and not is_active:
            join_time = self._voice_join_times.pop(key, None)
            if join_time is not None:
                async with self._xp_batch_lock:
                    self._award_voice_xp(member.guild.id, member.id, join_time)

    @tasks.loop(minutes=10.0)
    async def voice_xp_sweep(self):
        """Periodic flush for long VC sessions — prevents XP loss on restart."""
        async with self._xp_batch_lock:
            now = discord.utils.utcnow().timestamp()
            for key in list(self._voice_join_times):
                join_time = self._voice_join_times[key]
                guild_id, user_id = key
                self._award_voice_xp(guild_id, user_id, join_time)
                self._voice_join_times[key] = now  # reset to now

    @voice_xp_sweep.before_loop
    async def before_voice_sweep(self):
        await self.bot.wait_until_ready()

    # -- Message XP listener --

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.guild is None:
            return
        if not isinstance(message.author, discord.Member):
            return

        guild_id = message.guild.id
        user_id = message.author.id
        cfg = self._get_config(guild_id)

        if not cfg['enabled']:
            return

        now = message.created_at.timestamp()
        key = (guild_id, user_id)
        msg_len = len(message.content)

        # Cooldown check
        last = self._xp_cooldowns.get(key, 0.0)
        if now - last >= cfg['cooldown']:
            self._xp_cooldowns[key] = now
            xp = random.randint(cfg['xp_min'], cfg['xp_max'])
        else:
            xp = 0

        # Always track message count and longest message, even if on cooldown
        async with self._xp_batch_lock:
            self._xp_batch.append({
                'guild': guild_id,
                'user': user_id,
                'xp': xp,
                'message_count': 1,
                'longest_message': msg_len,
                'voice_minutes': 0,
            })

    # -- Commands --

    async def cog_command_error(self, ctx: Context, error: commands.CommandError):
        if isinstance(error, commands.BadArgument):
            await ctx.send(str(error), ephemeral=True)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.guild_only()
    @app_commands.describe(member='The member whose profile to view')
    async def profile(
        self,
        ctx: Context,
        *,
        member: Annotated[Union[discord.Member, discord.User], DisambiguateMember] = None,
    ):
        """View a member's server profile with XP, level, and stats."""
        member = member or ctx.author
        guild_id = ctx.guild.id
        cfg = self._get_config(guild_id)
        base = cfg['level_formula']

        row = await self.bot.pool.fetchrow(
            """SELECT xp, message_count, longest_message, voice_minutes,
                      (SELECT COUNT(*) + 1 FROM guild_profiles gp2
                       WHERE gp2.guild_id = gp.guild_id AND gp2.xp > gp.xp) AS rank
               FROM guild_profiles gp
               WHERE guild_id = $1 AND user_id = $2""",
            guild_id,
            member.id,
        )

        if row:
            xp = row['xp']
            message_count = row['message_count']
            longest_message = row['longest_message']
            voice_mins = row['voice_minutes']
            rank = row['rank']
        else:
            xp = 0
            message_count = 0
            longest_message = 0
            voice_mins = 0
            rank = None

        level, xp_progress, xp_needed = xp_to_next_level(xp, base)
        next_total = xp_for_level(level + 1, base)

        e = discord.Embed(colour=getattr(member, 'top_role', discord.Colour.blurple()).colour if isinstance(member, discord.Member) else discord.Colour.blurple())
        e.set_author(name=member.display_name, icon_url=member.display_avatar.with_format('png'))

        e.add_field(name='Level', value=str(level))
        e.add_field(name='XP', value=f'{xp:,} / {next_total:,}')
        e.add_field(name='Rank', value=f'#{rank:,}' if rank else 'Unranked')

        if isinstance(member, discord.Member) and member.joined_at:
            e.add_field(name='Joined', value=discord.utils.format_dt(member.joined_at, 'R'))

        e.add_field(name='Messages', value=f'{message_count:,}')
        e.add_field(name='Voice Time', value=format_voice_time(voice_mins))

        if longest_message > 0:
            e.add_field(name='Longest Message', value=f'{longest_message:,} chars')

        await ctx.send(embed=e)

    @commands.hybrid_command()
    @commands.guild_only()
    @app_commands.guild_only()
    async def leaderboard(self, ctx: Context):
        """View the server XP leaderboard."""
        rows = await self.bot.pool.fetch(
            """SELECT user_id, xp, message_count, voice_minutes
               FROM guild_profiles
               WHERE guild_id = $1
               ORDER BY xp DESC
               LIMIT 100""",
            ctx.guild.id,
        )

        if not rows:
            return await ctx.send('No one has earned XP yet!')

        cfg = self._get_config(ctx.guild.id)
        base = cfg['level_formula']

        entries = []
        for row in rows:
            level = get_level(row['xp'], base)
            entries.append(
                f'<@{row["user_id"]}> -- Level {level} ({row["xp"]:,} XP)'
            )

        pages = SimplePages(entries, ctx=ctx, per_page=10)
        pages.embed.title = f'{ctx.guild.name} Leaderboard'
        pages.embed.colour = discord.Colour.gold()
        await pages.start()


async def setup(bot: Mercybot):
    await bot.add_cog(Profile(bot))
