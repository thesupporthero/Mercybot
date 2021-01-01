
#Need to create categoires for mod differet types of logging
from discord.ext import commands
import aiohttp
import asyncio
import discord
from Admin import sql
#We actually already have a pretty sick way of handling SQL events. So we are just going to call that command. This means when we handle Sql events, we can just write it nativally.

#we need to pull the guild ID for when events and commands happen. This will be the key to in our DBtable.

ML_table = ModLog
#this stores the table we need, because it looks cool. Shh

# we need two tables, one is the guild id, other is mod-log channel(s). For we will just have light logging(Message edits/deletes, join leaves)
@commands.group(pass_context=True)
    async def modlog(self, ctx):
        """Sets up the channel that this command is ran in."""
        GUILD_ID = discord.Guild.id
        CID = ctx.channel.id
        sql = sql()
        try:
            sql(INSERT INTO ModLog (GuildID,MLCID)
            VALUES( {GuildID}, {MLCID});)
        except:
            print("Something went wrong")
            #<sql code here>
            #We are basically going to first find out if a mod log is already setup. To do this, we simply check if MODLOG contains a our guild ID

#@commands.modlog()
#async def enable():
#    """Enables logging. 
#    For now this is basic, just so I can get a feel for how I want to move forward.
#   In the future there will be more options and customizations."""
    #Lul so we need to make some code that takes a channel ID provided and then saves it into the SQL Database.

#@commands.modlog()
#async def exclude():
#    """Exclude a channel from logging"""
    #*sigh* so we need a way to exclude channels from logging. So we need to add an attribute to a servers entry that allows us to filter out events from that channel. 

#@commands.listener()
#So, place holder, but we need to take an event on a server and find out if logging for that event should be done. Good luck


#Don't forget to breing it all together, So insert the magic code below.
