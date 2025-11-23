import discord
import os
import asyncio
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = os.getenv('GUILD_ID') 

intents = discord.Intents.default()
intents.message_content = True

class FortniteBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=commands.DefaultHelpCommand()
        )

    async def setup_hook(self):
        await self.load_extension('cogs.fortnite')
        print("✅ Fortnite Cog loaded.")
        
        try:
            if GUILD_ID:
                guild_object = discord.Object(id=int(GUILD_ID))
                self.tree.copy_global_to(guild=guild_object)
                await self.tree.sync(guild=guild_object)
                print(f"🔁 Synced commands to guild {GUILD_ID} (Instant)")
            else:
                await self.tree.sync()
                print("🔁 Synced globally (May take 1 hour to update)")
        except Exception as e:
            print(f"⚠️ Sync Error: {e}")

    async def on_ready(self):
        print(f'🤖 Logged in as {self.user} (ID: {self.user.id})')
        print('------')

async def main():
    if not DISCORD_TOKEN:
        print("❌ Error: DISCORD_TOKEN not found in .env")
        return
        
    bot = FortniteBot()
    async with bot:
        await bot.start(DISCORD_TOKEN)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass