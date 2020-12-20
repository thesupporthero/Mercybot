import randomcolor
from discord.ext import commands, tasks
import discord
import asyncio
import asyncpg
import datetime
import textwrap

rand_color = randomcolor.RandomColor
class randomcolors(commands.Cog):
    """changes role colors"""
    def __init__(self, bot):
        self.bot = bot
        self._have_data = asyncio.Event(loop=bot.loop)
        self._current_timer = None
        self._task = bot.loop

    def cog_unload(self):
     self._task.cancel()
    
    
    @tasks.loop(minutes=1)
    async def cog_load(self, role: discord.Role = 773633451738923018):
        color = random.randint(0, 0xffffff)
        await role.edit(color=color)


def setup(bot):
    bot.add_cog(randomcolors(bot))