from __future__ import annotations
from typing_extensions import Annotated
from typing import TYPE_CHECKING, Optional

from .utils.translator import translate

from discord.ext import commands, tasks
import discord
import io
import random

if TYPE_CHECKING:
    from bot import Mercybot
    from .utils.context import Context

GUILD_ID = 8188301628827648
VOICE_ROOM_ID = 63346671803511605
GENERAL_VOICE_ID = 8188301630924800


class Funhouse(commands.Cog):
    def __init__(self, bot: Mercybot):
        self.bot: Mercybot = bot
        self.color_roles: dict[int, int] = {}
        self.rotate_role_colors.start()

    async def cog_load(self):
        query = "SELECT guild_id, role_id FROM guild_role_color;"
        rows = await self.bot.pool.fetch(query)
        self.color_roles = {r['guild_id']: r['role_id'] for r in rows}

    async def cog_unload(self):
        self.rotate_role_colors.cancel()

    @tasks.loop(hours=24)
    async def rotate_role_colors(self):
        for guild_id, role_id in list(self.color_roles.items()):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            role = guild.get_role(role_id)
            if role is None:
                continue
            color = discord.Color.from_rgb(
                random.randint(0, 255),
                random.randint(0, 255),
                random.randint(0, 255),
            )
            await role.edit(color=color)

    @rotate_role_colors.before_loop
    async def before_rotate(self):
        await self.bot.wait_until_ready()

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='\N{MAPLE LEAF}')

    def is_outside_voice(self, state: discord.VoiceState) -> bool:
        return state.channel is None or state.channel.id != GENERAL_VOICE_ID

    def is_inside_voice(self, state: discord.VoiceState) -> bool:
        return state.channel is not None and state.channel.id == GENERAL_VOICE_ID

    @commands.group(name='rolecolor', invoke_without_command=True)
    @commands.guild_only()
    async def rolecolor(self, ctx: Context):
        """Manages automatic role color rotation."""
        await ctx.send_help(ctx.command)

    @rolecolor.command(name='set')
    @commands.guild_only()
    async def rolecolor_set(self, ctx: Context, role: discord.Role):
        """Sets a role to have its color randomized every 24 hours. Guild owner only."""
        if ctx.author != ctx.guild.owner:
            return await ctx.send('Only the server owner can use this command.')
        query = """INSERT INTO guild_role_color(guild_id, role_id)
                   VALUES ($1, $2)
                   ON CONFLICT (guild_id) DO UPDATE SET role_id = $2;"""
        await self.bot.pool.execute(query, ctx.guild.id, role.id)
        self.color_roles[ctx.guild.id] = role.id
        await ctx.send(f'Role `{role.name}` will have its color randomized every 24 hours.')

    @rolecolor.command(name='stop')
    @commands.guild_only()
    async def rolecolor_stop(self, ctx: Context):
        """Stops the automatic color rotation. Guild owner only."""
        if ctx.author != ctx.guild.owner:
            return await ctx.send('Only the server owner can use this command.')
        if ctx.guild.id not in self.color_roles:
            return await ctx.send('No role color rotation is active.')
        query = "DELETE FROM guild_role_color WHERE guild_id = $1;"
        await self.bot.pool.execute(query, ctx.guild.id)
        self.color_roles.pop(ctx.guild.id)
        await ctx.send('Role color rotation stopped.')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.guild.id != GUILD_ID:
            return

        voice_room: Optional[discord.TextChannel] = member.guild.get_channel(VOICE_ROOM_ID)  # type: ignore
        if voice_room is None:
            return

        if self.is_outside_voice(before) and self.is_inside_voice(after):
            # joined a channel
            await voice_room.set_permissions(member, read_messages=True)
        elif self.is_outside_voice(after) and self.is_inside_voice(before):
            # left the channel
            await voice_room.set_permissions(member, read_messages=None)

    @commands.command(hidden=True)
    async def cat(self, ctx: Context):
        """Gives you a random cat."""
        async with ctx.session.get('https://api.thecatapi.com/v1/images/search') as resp:
            if resp.status != 200:
                return await ctx.send('No cat found :(')
            js = await resp.json()
            await ctx.send(embed=discord.Embed(title='Random Cat').set_image(url=js[0]['url']))

    @commands.command(hidden=True)
    async def dog(self, ctx: Context):
        """Gives you a random dog."""
        async with ctx.session.get('https://random.dog/woof') as resp:
            if resp.status != 200:
                return await ctx.send('No dog found :(')

            filename = await resp.text()
            url = f'https://random.dog/{filename}'
            filesize = ctx.guild.filesize_limit if ctx.guild else 8388608
            if filename.endswith(('.mp4', '.webm')):
                async with ctx.typing():
                    async with ctx.session.get(url) as other:
                        if other.status != 200:
                            return await ctx.send('Could not download dog video :(')

                        if int(other.headers['Content-Length']) >= filesize:
                            return await ctx.send(f'Video was too big to upload... See it here: {url} instead.')

                        fp = io.BytesIO(await other.read())
                        await ctx.send(file=discord.File(fp, filename=filename))
            else:
                await ctx.send(embed=discord.Embed(title='Random Dog').set_image(url=url))

    @commands.command(hidden=True)
    async def translate(self, ctx: Context, *, message: Annotated[Optional[str], commands.clean_content] = None):
        """Translates a message to English using Google translate."""

        loop = self.bot.loop
        if message is None:
            reply = ctx.replied_message
            if reply is not None:
                message = reply.content
            else:
                return await ctx.send('Missing a message to translate')

        try:
            result = await translate(message, session=self.bot.session)
        except Exception as e:
            return await ctx.send(f'An error occurred: {e.__class__.__name__}: {e}')

        embed = discord.Embed(title='Translated', colour=0x4284F3)
        embed.add_field(name=f'From {result.source_language}', value=result.original, inline=False)
        embed.add_field(name=f'To {result.target_language}', value=result.translated, inline=False)
        await ctx.send(embed=embed)


async def setup(bot: Mercybot):
    await bot.add_cog(Funhouse(bot))
