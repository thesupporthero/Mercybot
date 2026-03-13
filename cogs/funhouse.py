from __future__ import annotations
from typing_extensions import Annotated
from typing import TYPE_CHECKING, Optional

from .utils.translator import translate

from discord import app_commands
from discord.ext import commands
import discord
import io
import random
import pathlib

SPECIAL_CAT_PATH = pathlib.Path(__file__).parent.parent / 'assets' / 'special_cat.png'

if TYPE_CHECKING:
    from bot import Mercybot
    from .utils.context import Context

GUILD_ID = 8188301628827648
VOICE_ROOM_ID = 63346671803511605
GENERAL_VOICE_ID = 8188301630924800


class Funhouse(commands.Cog):
    def __init__(self, bot: Mercybot):
        self.bot: Mercybot = bot

    @property
    def display_emoji(self) -> discord.PartialEmoji:
        return discord.PartialEmoji(name='\N{MAPLE LEAF}')

    def is_outside_voice(self, state: discord.VoiceState) -> bool:
        return state.channel is None or state.channel.id != GENERAL_VOICE_ID

    def is_inside_voice(self, state: discord.VoiceState) -> bool:
        return state.channel is not None and state.channel.id == GENERAL_VOICE_ID

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

    @commands.hybrid_command()
    async def cat(self, ctx: Context):
        """Gives you a random cat."""
        if random.random() < 0.10 and SPECIAL_CAT_PATH.exists():
            await ctx.send(file=discord.File(SPECIAL_CAT_PATH, filename='special_cat.png'))
            return
        async with ctx.session.get('https://api.thecatapi.com/v1/images/search') as resp:
            if resp.status != 200:
                return await ctx.send('No cat found :(')
            js = await resp.json()
            await ctx.send(embed=discord.Embed(title='Random Cat').set_image(url=js[0]['url']))

    @commands.hybrid_command()
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
