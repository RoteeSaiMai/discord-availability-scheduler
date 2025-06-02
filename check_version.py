import discord, sys
print("python", sys.version)
print("discord.py", discord.__version__)
print("has create_poll:", hasattr(discord.TextChannel, "create_poll"))
