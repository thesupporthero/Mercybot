
import os
import asyncio
import functools
import itertools
import math
import random
import time
import discord
import json
import requests
import randomcolor

from async_timeout import timeout
from discord.ext import commands, tasks
from .utils import db, checks

rand_color = randomcolor.RandomColor
def check_DEV(ctx):
      return ctx.message.author.id == 450044263720288257
def check_CODEV(ctx):
      return ctx.message.author.id == 382550762875518986

class Reactions(commands.Cog, name='Reactions'):
  """RP stuff and boops"""
  def __init__(self, bot):
    self.bot = bot
    self._last_member = None

  #@commands.Cog.listener()
  #async def on_member_join(self, member):
   # channel = member.guild.system_channel
    #if channel is not None:
     #embed=discord.Embed(title=f"Welcome to the server {member.name}!", color=0xec59c8)
     #embed.set_image(url="https://media.giphy.com/media/RIe4xlUvLBVVYpZtNg/giphy.gif")
     #embed.set_footer(text="Please follow the rules! ^.^")
     #await channel.send(embed=embed)
  #@commands.command()
  #async def chant(self, *,ctx):
   # """uwu"""
   # if 
   # await ctx.send("Beat them up, Beat them up, Beat them up, Beat them up, Beat them up, Beat them up.")
  @commands.command()
  async def hello(self, ctx, *, member: discord.User = None):
    """Says hello to you"""
    member = member or ctx.author
    if ctx.author.id == self.bot.owner_id:
      await ctx.send('whoa, I know you from somewhere')
    if self._last_member is None or self._last_member.id != member.id:
      await ctx.send('Hello {0.mention} ^.^'.format(member))
    else:
      await ctx.send('Hello {0.mention}... This feels familiar.'.format(member))
      self._last_member = member
  @commands.command()
  async def owner(self, ctx):
    await ctx.send(self.bot.owner_id)
  @commands.command()
  async def greet(self, ctx, *, member: discord.User = None):
    """Greets a user you tag"""
    variable = [
      "Hello",
      "Hello there",
      "Greetings",
      "Hallo zusammen",
    ]
    greeting = "{}".format(random.choice(variable))

    if not member:
     await ctx.send("{} {0.mention}!".format(greeting))
    else:
     await ctx.send("{} {}!".format(greeting, member.mention))
     
  @commands.command()
  async def boop(self, ctx, *, member: discord.User = None):
    """boop!"""
    variable = [
      "<a:gassy:798233801196830801>",
      "<:ghostderp:796597978483392595>",
    ]
    izzys = "{}".format(random.choice(variable))

    if not member:
      await ctx.send("{}".format(izzys))


  @commands.command()
  async def pat(self, ctx, *, member: discord.User = None):
    """Pats a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=pat-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" has patted you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="UWU")
     await ctx.send(embed=embed)
    else:
      embed=discord.Embed(title="T-thank you!", color=0xec59c8)
      embed.set_image(url='https://cdn.discordapp.com/attachments/704446238422204476/800911677733470248/Z.png')
      await ctx.send(embed=embed)

  @commands.command()
  async def hug(self, ctx, *, member: discord.User = None):
    """Hugs a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=hug-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" has hugged you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="UWU")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")
  
  @commands.command()
  async def bite(self, ctx, *, member: discord.User = None):
    """Hugs a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=bite-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" has bit you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="ow")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")

  @commands.command()
  async def lick(self, ctx, *, member: discord.User = None):
    """Hugs a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=lick-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" has licked you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="uwu")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")

  @commands.command()
  async def dance(self, ctx, *, member: discord.User = None):
    """Dances with a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=dance-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" is dancing with you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="UWU")
     await ctx.send(embed=embed)
    else:
      response = requests.get('https://api.tenor.com/v1/search?q=dance-anime&key=ZCLO5M7CU85U&limit=20')
      data = json.loads(response.text)
      gif_choice = random.randint(0, 19)
      result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
      embed=discord.Embed(title="Yes I am dancing! Leave me alone :c", color=0xec59c8)
      embed.set_image(url=result_gif)
      embed.set_footer(text="UWU")
      await ctx.send(embed=embed)

  @commands.command()
  async def cuddle(self, ctx, *, member: discord.User = None):
    """Cuddles with a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=cuddle-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" is cuddling you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="UWU")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")

  @commands.command()
  async def poke(self, ctx, *, member: discord.User = None):
    """pokes a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=poke-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" has poked you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="UWU")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")

  @commands.command()
  async def kiss(self, ctx, *, member: discord.User = None):
    """kisses a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=kiss-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" has kissed you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="UWU")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")

  @commands.command()
  async def slap(self, ctx, *, member: discord.User = None):
    """Slaps a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=slap-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" has slapped you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="oof")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")

  @commands.command()
  async def rez(self, ctx, *, member: discord.User = None):
    """Rez's a user you tag"""
    variable = [
      "https://cdn.discordapp.com/attachments/704446238422204476/705091399263059988/Rez_gif.gif",
    ]
    if member:
     embed=discord.Embed(title=f"I am not a miracle worker you know, well sometimes. Fine I will rez "+ctx.message.author.name+"!", color=0xec59c8)

     embed.set_image(url="{}".format(random.choice(variable)))
     embed.set_footer(text="UWU")
     await ctx.send(embed=embed)

  @commands.command()
  async def stare(self, ctx, *, member: discord.User = None):
    """Stare at a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=stare-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" is staring at you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="uh oh")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")

  @commands.command()
  async def cry(self, ctx, *, member: discord.Member = None, user: discord.User = None):
    """I cry big tears, it's not pretty."""
    if not member:
     response = requests.get('https://api.tenor.com/v1/search?q=cry-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title="Aww feel better "+ctx.message.author.name+"!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="Everything is going to be okay!")
     await ctx.send(embed=embed)
    else:
     response = requests.get('https://api.tenor.com/v1/search?q=cry-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed2=discord.Embed(title="Aw, {}, {} is crying at you.".format(member.name, ctx.message.author.name), color=0xec59c8)
     embed2.set_image(url=result_gif)
     embed2.set_footer(text="What did you do!?")
     await ctx.send(embed=embed2)

  @commands.command()
  async def happy(self, ctx, *, member: discord.Member = None, user: discord.User = None):
    """I cry big tears, it's not pretty."""
    if not member:
     response = requests.get('https://api.tenor.com/v1/search?q=happy-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title="You are looking pretty happy there "+ctx.message.author.name+"!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="Such happy!")
     await ctx.send(embed=embed)
    else:
     response = requests.get('https://api.tenor.com/v1/search?q=happy-anime&key=ZCLO5M7CU85U&limit=20')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 19)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed2=discord.Embed(title="UWU seems, {}, {} is happy thanks to you.".format(member.name, ctx.message.author.name), color=0xec59c8)
     embed2.set_image(url=result_gif)
     embed2.set_footer(text="Yay!")
     await ctx.send(embed=embed2)

  @commands.command()
  async def kill(self, ctx, *, member: discord.User = None):
    if member:
     await ctx.send("Sorry {} I can't do that. That would be highly unethical.")

  @commands.command()
  async def pp(self, ctx, *, member: discord.User = None):
    """Someone said they would pay me to add this(they never did)"""
    variable = [
        "Your pp is big, congradulations!",
        "Your pp is small, that sucks.",]
    await ctx.send("{}".format(random.choice(variable)))

  @commands.command()
  async def spank(self, ctx, *, member: discord.User = None):
    """Spanks a user you tag"""
    if member:
     response = requests.get('https://api.tenor.com/v1/search?q=anime-spank&key=ZCLO5M7CU85U&limit=10')
     data = json.loads(response.text)
     gif_choice = random.randint(0, 10)
     result_gif = data['results'][gif_choice]['media'][0]['gif']['url']
     embed=discord.Embed(title=ctx.message.author.name+" is spanking you!", color=0xec59c8)
     embed.set_image(url=result_gif)
     embed.set_footer(text="what did you do?")
     await ctx.send(embed=embed)
    else:
      await ctx.send("oops you forgot to mention someone")
  
  @commands.command()
  async def trash(self, ctx, *, member: discord.User = None):
     embed=discord.Embed(title="ight, I am out", color=(random.randint(0, 0xffffff)))
     embed.set_image(url="https://cdn.discordapp.com/attachments/704446238422204476/773729435442348082/bye.gif")
     embed.set_footer(text="RIP "+ctx.message.author.name)
     await ctx.send(embed=embed)
     
  @commands.command()
  async def color(self, ctx):
    """Gives you a random color"""
    color = random.randint(0, 0xffffff)
    embed=discord.Embed(title="Here is your color:", color=color, description=color)
    await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Reactions(bot))