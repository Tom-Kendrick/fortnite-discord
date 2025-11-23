from cogs.fortnite_logic import Fortnite as FortniteCog


async def setup(bot):

    await bot.add_cog(FortniteCog(bot))
