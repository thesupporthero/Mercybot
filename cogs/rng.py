from discord.ext import commands
import random as rng
from collections import Counter
from typing import Optional
from .utils.formats import plural

class RNG(commands.Cog):
    """Utilities that provide pseudo-RNG."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(pass_context=True)
    async def random(self, ctx):
        """Displays a random thing you request."""
        if ctx.invoked_subcommand is None:
            await ctx.send(f'Incorrect random subcommand passed. Try {ctx.prefix}help random')

    @random.command()
    async def tag(self, ctx):
        """Displays a random tag.

        A tag showing up in this does not get its usage count increased.
        """
        tags = self.bot.get_cog('Tags')
        if tags is None:
            return await ctx.send('Tag commands currently disabled.')

        tag = await tags.get_random_tag(ctx.guild, connection=ctx.db)
        if tag is None:
            return await ctx.send('This server has no tags.')

        await ctx.send(f'Random tag found: {tag["name"]}\n{tag["content"]}')

    @random.command(name='map')
    async def _map(self, ctx):
        """Displays a random Splatoon 2 map."""
        splatoon = self.bot.get_cog('Splatoon')
        if splatoon is None:
            await ctx.send('Splatoon commands currently disabled.')
            return

        maps = splatoon.splat2_data.get('maps', [])
        if maps:
            await ctx.send(rng.choice(maps))

        del splatoon

    @random.command()
    async def mode(self, ctx):
        """Displays a random Splatoon mode."""
        mode = rng.choice(['Turf War', 'Splat Zones', 'Clam Blitz', 'Rainmaker', 'Tower Control'])
        await ctx.send(mode)

    @random.command()
    async def game(self, ctx):
        """Displays a random map/mode combination (no Turf War)"""
        splatoon = self.bot.get_cog('Splatoon')
        if splatoon is None:
            await ctx.send('Splatoon commands currently disabled.')
            return

        maps = splatoon.splat2_data.get('maps', [])
        if maps:
            mode = rng.choice(['Splat Zones', 'Tower Control', 'Rainmaker'])
            stage = rng.choice(maps)
            await ctx.send(f'{mode} on {stage}')

        del splatoon

    @random.command()
    async def number(self, ctx, minimum=0, maximum=100):
        """Displays a random number within an optional range.

        The minimum must be smaller than the maximum and the maximum number
        accepted is 1000.
        """

        maximum = min(maximum, 1000)
        if minimum >= maximum:
            await ctx.send('Maximum is smaller than minimum.')
            return

        await ctx.send(rng.randint(minimum, maximum))

    @random.command()
    async def lenny(self, ctx):
        """Displays a random lenny face."""
        lenny = rng.choice([
            "( ͡° ͜ʖ ͡°)", "( ͠° ͟ʖ ͡°)", "ᕦ( ͡° ͜ʖ ͡°)ᕤ", "( ͡~ ͜ʖ ͡°)",
            "( ͡o ͜ʖ ͡o)", "͡(° ͜ʖ ͡ -)", "( ͡͡ ° ͜ ʖ ͡ °)﻿", "(ง ͠° ͟ل͜ ͡°)ง",
            "ヽ༼ຈل͜ຈ༽ﾉ"
        ])
        await ctx.send(lenny)

    @commands.command()
    async def choose(self, ctx, *choices: commands.clean_content):
        """Chooses between multiple choices.

        To denote multiple choices, you should use double quotes.
        """
        if len(choices) < 2:
            return await ctx.send('Not enough choices to pick from.')

        await ctx.send(rng.choice(choices))

    @commands.command()
    async def choosebestof(self, ctx, times: Optional[int], *choices: commands.clean_content):
        """Chooses between multiple choices N times.

        To denote multiple choices, you should use double quotes.

        You can only choose up to 10001 times and only the top 10 results are shown.
        """
        if len(choices) < 2:
            return await ctx.send('Not enough choices to pick from.')

        if times is None:
            times = (len(choices) ** 2) + 1

        times = min(10001, max(1, times))
        results = Counter(rng.choice(choices) for i in range(times))
        builder = []
        if len(results) > 10:
            builder.append('Only showing top 10 results...')
        for index, (elem, count) in enumerate(results.most_common(10), start=1):
            builder.append(f'{index}. {elem} ({plural(count):time}, {count/times:.2%})')

        await ctx.send('\n'.join(builder))

def setup(bot):
    bot.add_cog(RNG(bot))
