from discord.ext import commands, tasks
from .utils import checks, db, time, cache
from .utils.formats import plural
from collections import Counter, defaultdict
from inspect import cleandoc

import re
import json
import discord
import enum
import datetime
import asyncio
import argparse, shlex
import logging
import asyncpg
import io
import random
log = logging.getLogger(__name__)


###need to have the following 
class GuildConfig(db.Table, table_name='guild_role_menu'):
    id = db.Column(db.Integer(big=True), primary_key=True)
    rm_options = db.Column(db.String(big=True))
    rm_reactid = db.Column(db.String(big=True))
## Configuration

class RoleMenuConfig:
    __slots__ = ('has_role_menu', 'id', 'bot', 'message_id', 'cat_name',
                 'react_IDs', 'arg_1', 'arg_2', 'arg_3', 'role_id', 'rm_options', 'rm_reactid')

    @classmethod
    async def from_record(cls, record, bot):
        self = cls()

        # the basic configuration
        self.bot = bot
        self.id = record['id']
        self.messageid = record['messageid']
        self.reactionids = set(record['safe_mention_channel_ids'] or [])
        self.reaction_statements = set(record['muted_members'] or [])
        self.role_ids = record['mute_role_id']
        self.modlog_enable = record['modlog_enable']
        self.modlog_chid = record['modlog_chid']
        return self
    @cache.cache() #yo this is kinda a work in progress so like none of this is right but it's call
    async def get_rolemenu_config(self, guild_id):
        query = """SELECT * FROM guild_role_menus WHERE id=$1;"""
        async with self.bot.pool.acquire(timeout=300.0) as con:
            record = await con.fetchrow(query, guild_id)
            if record is not None:
                return await ModConfig.from_record(record, self.bot)
            return None
    
    @property
    def messageid(self):
        guild = self.bot.get_guild(self.id)
        return guild and guild.get_channel(self.messageID)

    @property
    def mute_role(self):
        guild = self.bot.get_guild(self.id)
        return guild and self.mute_role_id and guild.get_role(self.mute_role_id)
    @property
    def modlog_channel(self):
        guild = self.bot.get_guild(self.id)
        return guild and guild.get_channel(self.modlog_chid)
    def is_muted(self, member):
        return member.id in self.muted_members

    async def apply_mute(self, member, reason):
        if self.mute_role_id:
            await member.add_roles(discord.Object(id=self.mute_role_id), reason=reason)


class RoleMenu(commands.Cog):
    """Role menus for your server"""
    def __init__(self, bot):
        self.bot = bot

    @commands.group(aliases=['Rolemenus'], invoke_without_command=True)
    @checks.is_mod()
    async def rolemenu(self, ctx):
        """Since you called this without any context, lets talk about bacon.
        Bacon is very good, but like hate cooking it. IDK the smoke is hard to breath and I am like,
        naw bro.\n
        \n
        Oh you want to know about your guilds rolemenus? \n
        Uh, well, you have come to the wrong place. Rolemenus are effort and so under appreciated.\n
        Like Seriously, I can't talk to `other` friends about this. They like rolemenus?\n
        And like you have like so many data points to track and keep together.\n
        Like the guildID, messageID, Role menu name, reactions, roles, and options we want with it.\n
        Sure it doesn't seem so complicated, but mind you the mod module is 2000 lines of code and we aren't even trying with that.\n
        ```Sigh.```"""
    #fancy code goes around here to give an overview of the role menus in a guild. 


    @rolemenu.command(name='add', alias='create')
    @checks.is_mod()
    async def Rolemenu_add(self, ctx, *, args, message):
        """Mass bans multiple members from the server.

        This command has a powerful "command line" syntax. To use this command
        you and the bot must both have Ban Members permission. **Every option is optional.**

        Users are only banned **if and only if** all conditions are met.

        The following options are valid.

        `--max`: Sets it so members can only set so many roles.
        `--reqrole`: Specify if they require a role before using this rolemenu.
        `--nonrem`: Prevents users from removing roles once assigned.
        `--DM`: DM members when they obtain a role.
        """

        # For some reason there are cases due to caching that ctx.author
        # can be a User even in a guild only context
        # Rather than trying to work out the kink with it
        # Just upgrade the member itself.
        if not isinstance(ctx.author, discord.Member):
            try:
                author = await ctx.guild.fetch_member(ctx.author.id)
            except discord.HTTPException:
                return await ctx.send('Somehow, Discord does not seem to think you are in this server.')
        else:
            author = ctx.author

        parser = Arguments(add_help=False, allow_abbrev=False)
        parser.add_argument('--max')
        parser.add_argument('--reqrole')
        parser.add_argument('--nonrem')
        parser.add_argument('--DM')