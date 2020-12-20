import randomcolor
from discord.ext import commands, tasks
import discord
import asyncio
import asyncpg
import datetime
import textwrap

rand_color = randomcolor.RandomColor
class randomcolors(commands.Cog):
    """Reminders to do something."""

    def __init__(self, bot):
        self.bot= bot
        self._batch = []
        self.lock = asyncio.Lock()
        self.bulker.start()

    @tasks.loop(minutes=1)
    async def change(self, ctx):
    server = 755367452279570453
    role = discord.utils.get(server.roles, name='colors')
     await client.edit_role(server, role, colour=rand_color)


def setup(bot):
    bot.add_cog(Randomcolors(bot))