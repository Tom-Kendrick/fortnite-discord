import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import base64
import zlib
import os
import datetime

CLIENT_ID = "3f69e56c7649492c8cc29f1af08a8a12"
CLIENT_SECRET = "b51ee9cb12234f50a69efa67ef53812e"
AUTH_HEADER = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

class Fortnite(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auth_file = "device_auths.json"
        self.fngg_cache = None
        self.fngg_cache_time = None

    def get_auth_details(self, name):
        if not os.path.exists(self.auth_file):
            return None, None
        
        try:
            with open(self.auth_file, 'r') as f:
                data = json.load(f)
            for key, value in data.items():
                if key.lower() == name.lower():
                    return value, key 
            return None, None
        except Exception as e:
            print(f"Error loading auth file: {e}")
            return None, None

    async def get_fngg_map(self, session):
        if not self.fngg_cache or not self.fngg_cache_time or (datetime.datetime.now() - self.fngg_cache_time).total_seconds() > 3600:
            try:
                async with session.get("https://fortnite.gg/api/items.json") as resp:
                    if resp.status == 200:
                        self.fngg_cache = await resp.json()
                        self.fngg_cache_time = datetime.datetime.now()
                        print("Refreshed FNGG Item Cache")
            except Exception as e:
                print(f"Failed to fetch FNGG cache: {e}")
        return self.fngg_cache

    async def _authenticate(self, session, device_auths):
        token_url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
        token_payload = {
            "grant_type": "device_auth",
            "account_id": device_auths.get('account_id'),
            "device_id": device_auths.get('device_id'),
            "secret": device_auths.get('secret')
        }
        token_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {AUTH_HEADER}"
        }

        async with session.post(token_url, data=token_payload, headers=token_headers) as resp:
            if resp.status != 200:
                return None, await resp.text()
            return await resp.json(), None

    @commands.hybrid_command(name="vbucks", description="Check V-Bucks balance")
    @app_commands.describe(name="The account name stored in device_auths.json")
    async def vbucks(self, ctx, *, name: str = "ShrillKangaroo"):
        await ctx.defer()
        status_msg = await ctx.send(f"🔄 Authenticating as **{name}**...")

        device_auths, proper_name = self.get_auth_details(name)
        if not device_auths:
            await status_msg.edit(content=f"❌ Profile **{name}** not found in `device_auths.json`.")
            return

        async with aiohttp.ClientSession() as session:
            token_data, error = await self._authenticate(session, device_auths)
            if error:
                await status_msg.edit(content=f"❌ Auth failed: `{error}`")
                return

            access_token = token_data['access_token']
            account_id = token_data['account_id']
            display_name = token_data.get('displayName', 'Unknown')

            api_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}

            common_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=common_core&rvn=-1"
            total_vbucks = 0
            
            async with session.post(common_url, json={}, headers=api_headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'profileChanges' in data:
                        for change in data['profileChanges']:
                            if 'profile' in change and 'items' in change['profile']:
                                items = change['profile']['items']
                                for item_data in items.values():
                                    template_id = item_data.get('templateId', '')
                                    if template_id.startswith("Currency:Mtx"):
                                        quantity = item_data.get('quantity', 0)
                                        attr = item_data.get('attributes', {})
                                        platform = attr.get('platform', 'Shared') if attr else 'Shared'
                                        if platform != "Nintendo":
                                            total_vbucks += quantity
                else:
                    await status_msg.edit(content=f"❌ Failed to fetch profile: HTTP {resp.status}")
                    return

            embed = discord.Embed(title=f"💰 V-Bucks: {display_name}", color=discord.Color.green())
            embed.description = f"## **{total_vbucks:,}** V-Bucks"
            embed.set_footer(text=f"Account ID: {account_id}")
            
            await status_msg.edit(content=None, embed=embed)

    @commands.hybrid_command(name="locker", description="Generate a Fortnite.GG locker link")
    @app_commands.describe(name="The account name stored in device_auths.json")
    async def locker(self, ctx, *, name: str = "ShrillKangaroo"):
        await ctx.defer()
        status_msg = await ctx.send(f"🔄 Generating Locker for **{name}**...")

        device_auths, proper_name = self.get_auth_details(name)
        if not device_auths:
            await status_msg.edit(content=f"❌ Profile **{name}** not found in `device_auths.json`.")
            return

        async with aiohttp.ClientSession() as session:
            token_data, error = await self._authenticate(session, device_auths)
            if error:
                await status_msg.edit(content=f"❌ Auth failed: `{error}`")
                return

            access_token = token_data['access_token']
            account_id = token_data['account_id']
            display_name = token_data.get('displayName', 'Unknown')

            api_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}

            owned_ids = []
            creation_date = ""
            locker_counts = {"AthenaCharacter": 0, "AthenaDance": 0, "AthenaPickaxe": 0, "AthenaGlider": 0}

            common_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=common_core&rvn=-1"
            async with session.post(common_url, json={}, headers=api_headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'profileChanges' in data:
                        for change in data['profileChanges']:
                            if 'profile' in change and 'items' in change['profile']:
                                items = change['profile']['items']
                                for item_data in items.values():
                                    template_id = item_data.get('templateId', '')
                                    if "HomebaseBannerIcon" in template_id:
                                        owned_ids.append(template_id.split(":")[1].lower())

            athena_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=athena&rvn=-1"
            async with session.post(athena_url, json={}, headers=api_headers) as resp:
                if resp.status == 200:
                    athena_data = await resp.json()
                    if 'profileChanges' in athena_data:
                        profile_block = athena_data['profileChanges'][0]['profile']
                        creation_date = profile_block.get('created', '')
                        items = profile_block.get('items', {})
                        for item_data in items.values():
                            template_id = item_data.get('templateId', '')
                            parts = template_id.split(':')
                            if len(parts) > 1:
                                i_type = parts[0]
                                i_id = parts[1]
                                owned_ids.append(i_id.lower())
                                if i_type in locker_counts:
                                    locker_counts[i_type] += 1
                else:
                    await status_msg.edit(content=f"❌ Failed to fetch locker: HTTP {resp.status}")
                    return

            fngg_map = await self.get_fngg_map(session)
            locker_link = None
            if fngg_map:
                fngg_lookup = {k.lower(): v for k, v in fngg_map.items()}
                fngg_ids = [int(fngg_lookup[item]) for item in owned_ids if item in fngg_lookup]
                fngg_ids.sort()
                
                if fngg_ids:
                    deltas = [str(val) if i == 0 else str(val - fngg_ids[i-1]) for i, val in enumerate(fngg_ids)]
                    payload = f"{creation_date},{','.join(deltas)}"
                    compressor = zlib.compressobj(level=-1, method=zlib.DEFLATED, wbits=-9, memLevel=zlib.DEF_MEM_LEVEL, strategy=zlib.Z_DEFAULT_STRATEGY)
                    compressed = compressor.compress(payload.encode()) + compressor.flush()
                    locker_link = f"https://fortnite.gg/my-locker?items={base64.urlsafe_b64encode(compressed).decode().rstrip('=')}"

            embed = discord.Embed(title=f"🎒 Locker: {display_name}", color=discord.Color.blue())
            stats_text = "\n".join([f"**{v}** {k.replace('Athena', '')}" for k, v in locker_counts.items()])
            embed.description = stats_text
            
            view = discord.ui.View()
            if locker_link:
                view.add_item(discord.ui.Button(label="View on Fortnite.GG", url=locker_link))
            else:
                view.add_item(discord.ui.Button(label="Link Unavailable", disabled=True))

            await status_msg.edit(content=None, embed=embed, view=view)