import discord
import re
import json
import enum
import datetime
import asyncio
import argparse, shlex
import logging
import asyncpg
import io
from discord.ext import commands, tasks
from .utils import checks, db, time, cache

x = 2

z = 1

class Currency(commands.Cog, name='Currency'):
  """Help text here"""
  def __init__(self, bot):
    self.bot = bot
#few things to think about when creating this. 
#First you will want to work with the db system as this is an easy method of storying code.
#second the bit below will be raised when someone talks. So lets break this down as you need it.
#    @commands.Cog.listener() #<this activates below
#    async def on_message(self, message):<this is just the event we are listening for.
#        author = message.author #<Us making it easier to use later.
#        if author.id in (self.bot.user.id, self.bot.owner_id): #<If we are a bot,
#           return #<then we stop the script.

#        if message.guild is None: <if the message is in dms we just nope out.
#            return
##
#Next sql isn't hard to deal with here as a most of the heavy lifting is handled for you by the bot.
#So key concepts to know, You will be working with a `table` that table holds rows, and columns.
#Columns are your data type you want to store.
#Name, Date_Of_Birth, eye_color
#Rows are your entries
#Suse, 08.08.1990, blue
#Each table has to have a column that doesn't allow dublicate entries, we call this a key, or index.
#For our purposes if we want a module to be guild centric, we just use the guildID as the key, as no two server will have the same ID.

#this pulls above together and makes it usable to the bot
def setup(bot):
    bot.add_cog(Currency(bot))