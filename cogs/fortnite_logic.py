import discord
from discord.ext import commands
from discord import app_commands
import aiohttp
import json
import base64
import zlib
import os
import datetime
import traceback

CLIENT_ID = "3f69e56c7649492c8cc29f1af08a8a12"
CLIENT_SECRET = "b51ee9cb12234f50a69efa67ef53812e"

AUTH_HEADER = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()

class LoginModal(discord.ui.Modal, title="Link Epic Account"):
    auth_code = discord.ui.TextInput(
        label="Authorization Code",
        placeholder="Paste the 32-character code here...",
        min_length=32,
        max_length=32,
        required=True
    )

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        code = self.auth_code.value
        
        async with aiohttp.ClientSession() as session:
            token_url = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
            payload = {
                "grant_type": "authorization_code",
                "code": code
            }
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {AUTH_HEADER}"
            }

            try:
                async with session.post(token_url, data=payload, headers=headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        await interaction.followup.send(f"❌ Code exchange failed: {resp.status}\n`{text}`", ephemeral=True)
                        return
                    data = await resp.json()
                    
                access_token = data['access_token']
                account_id = data['account_id']
                display_name = data.get('displayName', f"User_{account_id[:5]}")

                device_url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}/deviceAuth"
                device_headers = {"Authorization": f"Bearer {access_token}"}
                
                async with session.post(device_url, json={}, headers=device_headers) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        await interaction.followup.send(f"❌ Device Auth failed: {resp.status}\n`{text}`", ephemeral=True)
                        return
                    device_data = await resp.json()

                new_account = {
                    "account_name": display_name,
                    "account_id": account_id,
                    "device_id": device_data['deviceId'],
                    "secret": device_data['secret']
                }
                
                self.cog.save_account(interaction.user.id, new_account)
                
                embed = discord.Embed(title="✅ Account Linked", color=discord.Color.green())
                embed.description = f"Successfully linked **{display_name}** to your Discord user."
                embed.set_footer(text=f"ID: {account_id}")
                await interaction.followup.send(embed=embed, ephemeral=True)

            except Exception as e:
                await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)
                traceback.print_exc()

class LoginView(discord.ui.View):
    def __init__(self, cog, login_url):
        super().__init__(timeout=None)
        self.cog = cog
        self.add_item(discord.ui.Button(label="1. Get Auth Code", url=login_url, style=discord.ButtonStyle.link))

    @discord.ui.button(label="2. Submit Code", style=discord.ButtonStyle.success, custom_id="submit_auth_code")
    async def submit_code(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(LoginModal(self.cog))

class Fortnite(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.auth_file = "device_auths.json"
        self.fngg_cache = None
        self.fngg_cache_time = None
        self._ensure_auth_file()

    def _ensure_auth_file(self):
        if not os.path.exists(self.auth_file):
            with open(self.auth_file, 'w') as f:
                json.dump({}, f)

    def _load_auth_file(self):
        try:
            with open(self.auth_file, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def get_user_accounts(self, user_id):
        data = self._load_auth_file()
        return data.get(str(user_id), [])

    def get_auth_details(self, user_id, account_name=None):

        accounts = self.get_user_accounts(user_id)
        if not accounts:
            return None
        
        if account_name is None:
            return accounts[0]
            
        for acc in accounts:
            if acc.get("account_name", "").lower() == account_name.lower():
                return acc
        return None

    def save_account(self, user_id, new_account_data):
        data = self._load_auth_file()
        user_key = str(user_id)
        
        if user_key not in data:
            data[user_key] = []
            
        updated = False
        for i, acc in enumerate(data[user_key]):
            if acc.get("account_name", "").lower() == new_account_data["account_name"].lower():
                data[user_key][i] = new_account_data
                updated = True
                break
        
        if not updated:
            data[user_key].append(new_account_data)
            
        with open(self.auth_file, 'w') as f:
            json.dump(data, f, indent=4)

    async def get_fngg_map(self, session):
        if not self.fngg_cache or not self.fngg_cache_time or (datetime.datetime.now() - self.fngg_cache_time).total_seconds() > 3600:
            try:
                async with session.get("https://fortnite.gg/api/items.json") as resp:
                    if resp.status == 200:
                        self.fngg_cache = await resp.json()
                        self.fngg_cache_time = datetime.datetime.now()
                        print("🔄 Refreshed FNGG Item Cache")
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

    async def _get_account_vbucks(self, session, account_id, access_token):
        url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=common_core&rvn=-1"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}
        
        total = 0
        try:
            async with session.post(url, json={}, headers=headers) as resp:
                if resp.status != 200:
                    return 0, f"HTTP {resp.status}"
                
                data = await resp.json()
                json.dump(data, open("debug_profile.json", "w"), indent=4)
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
                                        total += quantity
            return total, None
        except Exception as e:
            return 0, str(e)

    @commands.hybrid_command(name="login", description="Add a new account to the bot")
    async def login(self, ctx):
        login_url = f"https://www.epicgames.com/id/api/redirect?clientId={CLIENT_ID}&responseType=code"
        
        embed = discord.Embed(title="🔑 Login to Fortnite", color=discord.Color.blue())
        embed.description = (
            "**Instructions:**\n"
            "1. Click the link button below to login to Epic Games.\n"
            "2. Copy the `authorizationCode` (it looks like `492a...`) from the text on the page.\n"
            "3. Click the **Submit Code** button and paste it."
        )
        
        view = LoginView(self, login_url)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="vbucks", description="Check V-Bucks balance")
    @app_commands.describe(name="Account name (leave empty for first account)")
    async def vbucks(self, ctx, *, name: str = None):
        await ctx.defer()
        
        device_auths = self.get_auth_details(ctx.author.id, name)
        
        if not device_auths:
            if name:
                await ctx.send(f"❌ Account `{name}` not found in your list.")
            else:
                await ctx.send("❌ You haven't added any accounts yet! Use `/login`.")
            return

        status_msg = await ctx.send(f"🔄 Checking **{device_auths['account_name']}**...")

        async with aiohttp.ClientSession() as session:
            token_data, error = await self._authenticate(session, device_auths)
            if error:
                await status_msg.edit(content=f"❌ Auth failed: `{error}`")
                return

            access_token = token_data['access_token']
            account_id = token_data['account_id']
            display_name = token_data.get('displayName', 'Unknown')

            vbucks_count, err = await self._get_account_vbucks(session, account_id, access_token)
            if err:
                await status_msg.edit(content=f"❌ Fetch failed: {err}")
                return

            embed = discord.Embed(title=f"💰 V-Bucks: {display_name}", color=discord.Color.green())
            embed.description = f"## **{vbucks_count:,}** V-Bucks"
            
            
            await status_msg.edit(content=None, embed=embed)

    @commands.hybrid_command(name="vbucksbulk", description="Check V-Bucks for ALL your accounts")
    async def vbucksbulk(self, ctx):
        await ctx.defer()
        

        
        my_accounts = self.get_user_accounts(ctx.author.id)
        
        if not my_accounts:
            await ctx.send("❌ You haven't added any accounts yet! Use `/login`.")
            return

        status_msg = await ctx.send(f"🔄 Checking {len(my_accounts)} accounts...")
        results = []
        grand_total = 0

        async with aiohttp.ClientSession() as session:
            for auth_details in my_accounts:
                name = auth_details['account_name']
                
                token_data, error = await self._authenticate(session, auth_details)
                if error:
                    results.append(f"❌ **{name}**: Auth Failed")
                    continue

                access_token = token_data['access_token']
                account_id = token_data['account_id']
                display_name = token_data.get('displayName', name)

                vbucks, err = await self._get_account_vbucks(session, account_id, access_token)
                if err:
                    results.append(f"⚠️ **{display_name}**: Failed ({err})")
                else:
                    results.append(f"✅ **{display_name}**: {vbucks:,}")
                    grand_total += vbucks

        embed = discord.Embed(title="💰 Bulk V-Bucks Report", color=discord.Color.gold())
        description = "\n".join(results)
        description += f"\n\n**GRAND TOTAL: {grand_total:,} V-Bucks**"
        embed.description = description
        embed.set_footer(text=f"Checked {len(my_accounts)} accounts for {ctx.author.name}")

        await status_msg.edit(content=None, embed=embed)

    def format_quest_info(self, item_data, daily_defs):
        template_id = item_data.get("templateId", "")
        attributes = item_data.get("attributes", {})
        
        clean_id = template_id.replace("Quest:", "").lower()
        
        current = 0
        objectives = attributes.get("objectives", [])
        if objectives:
            current = objectives[0].get("completionCount", 0)

        if clean_id in daily_defs:
            info = daily_defs[clean_id]
            quest_name = info.get("names", {}).get("en", clean_id)
            target = info.get("limit", 0)
            
            rewards = info.get("rewards", {})
            vbucks = rewards.get("mtx", 0)
            gold = rewards.get("gold", 0)

            reward_str = ""
            if vbucks > 0:
                reward_str = f" <:vbucks:> **{vbucks}**"
            elif gold > 0:
                reward_str = f" 🟡 **{gold}**"
                
            return f"• **{quest_name}**\n   `{current}/{target}` {reward_str}", vbucks
        
        fallback_name = clean_id.replace("daily_", "").replace("_", " ").title()
        return f"• **{fallback_name}** (Not in JSON)\n   `Progress: {current}`", 0


    @commands.hybrid_command(name="dailiesbulk", description="Check Daily Quests for ALL accounts")
    async def dailiesbulk(self, ctx):
        await ctx.defer()
        
        my_accounts = self.get_user_accounts(ctx.author.id)
        if not my_accounts:
            await ctx.send("❌ You haven't added any accounts yet! Use `/login`.")
            return

        daily_defs = {}
        json_path = "../constants/stw_dailies.json" 
        
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                daily_defs = json.load(f)
        except Exception as e:
            print(f"⚠️ Error loading {json_path}: {e}")

        status_msg = await ctx.send(f"🔄 Checking {len(my_accounts)} accounts...")
        
        embed = discord.Embed(title="📜 Bulk Daily Quests Report", color=discord.Color.purple())
        total_vbucks = 0
        total_quests = 0

        async with aiohttp.ClientSession() as session:
            for auth_details in my_accounts:
                token_data, error = await self._authenticate(session, auth_details)
                if error:
                    embed.add_field(name=f"👤 {auth_details['account_name']}", value="❌ Auth Failed", inline=False)
                    continue

                account_id = token_data['account_id']
                display_name = token_data.get('displayName', auth_details['account_name'])

                base_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client"
                headers = {"Authorization": f"Bearer {token_data['access_token']}", "Content-Type": "application/json"}
                params = {"profileId": "campaign", "rvn": "-1"}

                try:
                    await session.post(f"{base_url}/ClientQuestLogin", params=params, json={}, headers=headers)
                    
                    async with session.post(f"{base_url}/QueryProfile", params=params, json={}, headers=headers) as resp:
                        data = await resp.json()

                    items = data["profileChanges"][0]["profile"]["items"] if "profileChanges" in data else data.get("items", {})
                    
                    quest_lines = []
                    for item_data in items.values():
                        tid = item_data.get("templateId", "")
                        if tid.lower().startswith("quest:daily_") and item_data.get("attributes", {}).get("quest_state") == "Active":
                            quest_text, v_val = self.format_quest_info(item_data, daily_defs)
                            quest_lines.append(quest_text)
                            total_vbucks += v_val
                            total_quests += 1

                    val_text = "\n".join(quest_lines) if quest_lines else "✅ *All quests completed*"
                    embed.add_field(name=f"👤 {display_name}", value=val_text, inline=False)

                except Exception as e:
                    embed.add_field(name=f"👤 {display_name}", value=f"⚠️ Error: {str(e)[:50]}", inline=False)

        embed.set_footer(text=f"Total: {total_quests} Quests • {total_vbucks} V-Bucks Pending")
        await status_msg.edit(content=None, embed=embed)
        
    @commands.hybrid_command(name="locker", description="Generate a Fortnite.GG locker link")
    @app_commands.describe(name="Account name (leave empty for first account)")
    async def locker(self, ctx, *, name: str = None):
        await ctx.defer()

        device_auths = self.get_auth_details(ctx.author.id, name)
        if not device_auths:
            await ctx.send("❌ Account not found.")
            return

        status_msg = await ctx.send(f"🔄 Accessing locker for **{device_auths['account_name']}**...")

        try:
            async with aiohttp.ClientSession() as session:
                token_data, error = await self._authenticate(session, device_auths)
                if error:
                    await status_msg.edit(content=f"❌ Auth failed: `{error}`")
                    return

                access_token = token_data['access_token']
                account_id = token_data['account_id']
                display_name = token_data.get('displayName', 'Unknown')
                api_headers = {"Content-Type": "application/json", "Authorization": f"Bearer {access_token}"}

                await status_msg.edit(content=f"✅ Logged in. Fetching items...")

                owned_ids = []
                creation_date = ""
                locker_counts = {"AthenaCharacter": 0, "AthenaDance": 0, "AthenaPickaxe": 0, "AthenaGlider": 0}
                vbucks_count = 0

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
                                        if template_id.startswith("Currency:Mtx"):
                                            quantity = item_data.get('quantity', 0)
                                            attr = item_data.get('attributes', {})
                                            platform = attr.get('platform', 'Shared') if attr else 'Shared'
                                            if platform != "Nintendo":
                                                vbucks_count += quantity

                athena_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=athena&rvn=-1"
                async with session.post(athena_url, json={}, headers=api_headers) as resp:
                    if resp.status == 200:
                        athena_data = await resp.json()
                        if 'profileChanges' in athena_data:
                            change = athena_data['profileChanges'][0]
                            profile = change.get('profile', {})
                            creation_date = profile.get('created', '')
                            items = profile.get('items', {})
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
                        await status_msg.edit(content=f"❌ Failed to fetch locker.")
                        return

                await status_msg.edit(content="🔄 Generating Fortnite.GG link...")
                fngg_map = await self.get_fngg_map(session)
                locker_link = None
                
                if fngg_map:
                    fngg_lookup = {k.lower(): v for k, v in fngg_map.items()}
                    fngg_ids = []
                    for item in owned_ids:
                        if item in fngg_lookup:
                            try:
                                fngg_ids.append(int(fngg_lookup[item]))
                            except ValueError:
                                pass
                    fngg_ids.sort()
                    
                    if fngg_ids:
                        deltas = [str(val) if i == 0 else str(val - fngg_ids[i-1]) for i, val in enumerate(fngg_ids)]
                        payload_str = f"{creation_date},{','.join(deltas)}"
                        try:
                            compressor = zlib.compressobj(level=-1, method=zlib.DEFLATED, wbits=-9, memLevel=zlib.DEF_MEM_LEVEL, strategy=zlib.Z_DEFAULT_STRATEGY)
                            compressed_data = compressor.compress(payload_str.encode()) + compressor.flush()
                            encoded_str = base64.urlsafe_b64encode(compressed_data).decode().rstrip("=")
                            locker_link = f"https://fortnite.gg/my-locker?items={encoded_str}"
                        except:
                            pass

                embed = discord.Embed(title=f"🎒 Locker: {display_name}", color=discord.Color.blue())
                stats_text = "\n".join([f"**{v}** {k.replace('Athena', '')}" for k, v in locker_counts.items()])
                
                if locker_link:
                    stats_text += f"\n\n🔗 [**View on Fortnite.GG**]({locker_link})"
                else:
                    stats_text += "\n\n⚠️ Locker link unavailable."

                embed.description = stats_text
                embed.add_field(name="V-Bucks", value=f"{vbucks_count:,}", inline=False)
                
                
                view = discord.ui.View()
                if locker_link and len(locker_link) <= 512:
                    view.add_item(discord.ui.Button(label="View on Fortnite.GG", url=locker_link))
                else:
                    view.add_item(discord.ui.Button(label="Link in Description", disabled=True))

                await status_msg.edit(content=None, embed=embed, view=view)

        except Exception as e:
            traceback.print_exc()
            await status_msg.edit(content=f"❌ Error: `{e}`")

    @commands.hybrid_command(name="taxi", description="STW Taxi Service")
    @app_commands.describe(epic_name="Epic Username")
    async def taxi(self, ctx, epic_name: str = None):
        await ctx.defer()
        target_user = epic_name
        if target_user is None:
            account_data = self.get_auth_details(ctx.author.id)
            
            if not account_data:
                await ctx.send("❌ No name provided and no linked account found. Please use `/login` or type a name.", ephemeral=True)
                return
            
            target_user = account_data.get("account_name")

        url = "http://127.0.0.1:8080/taxi"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={"username": target_user}) as resp:
                    text = await resp.text()
                    
                    if resp.status == 200:
                        embed = discord.Embed(title="🚖 Taxi Dispatch", description=f"Joining **{target_user}**\n\n{text}", color=discord.Color.gold())
                        await ctx.send(embed=embed)
                    else:
                        await ctx.send(f"❌ Taxi Error: {text}")
        except Exception as e:
            await ctx.send(f"❌ Taxi Service is OFFLINE. (Error: {e})")


    @commands.hybrid_command(name="dailies", description="STW Daily Quests")
    @app_commands.describe(name="Account name (leave empty for first account)")
    async def dailies(self, ctx, *, name: str = None):
        await ctx.defer()

        device_auths = self.get_auth_details(ctx.author.id, name)
        if not device_auths:
            await ctx.send("❌ Account not found.")
            return

        
        profile_url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{auth['account_id']}/client/QueryProfile?profileId=campaign&rvn=-1"
        async with aiohttp.ClientSession() as session:
            async with session.post(
                profile_url, 
                json={}, 
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    await ctx.send(f"❌ Failed to fetch profile: {resp.status}")
                    return
                
                data = await resp.json()

        quests = []
        try:
            profile_changes = data.get("profileChanges", [])
            if not profile_changes:
                await ctx.send("❌ No profile data found.")
                return
                
            items = profile_changes[0].get("profile", {}).get("items", {})
            
            for item_id, item_data in items.items():
                template_id = item_data.get("templateId", "")
                
                if template_id.startswith("Quest:daily_") and item_data["attributes"].get("quest_state") == "Active":
                    raw_name = template_id.split("daily_")[-1].replace("_", " ").title()
                    
                    attributes = item_data.get("attributes", {})
                    current_progress = 0
                    
                    for key, val in attributes.items():
                        if key.startswith("completion_"):
                            current_progress = val
                            break
                    
                    quests.append(f"📜 **{raw_name}**\n   Progress: `{current_progress}`")

        except Exception as e:
            await ctx.send(f"❌ Error parsing quests: {e}")
            return

        if quests:
            embed = discord.Embed(
                title=f"📅 Daily Quests for {auth['account_name']}",
                description="\n\n".join(quests),
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send("✅ You have no active Daily Quests!")


async def setup(bot):
    await bot.add_cog(Fortnite(bot))