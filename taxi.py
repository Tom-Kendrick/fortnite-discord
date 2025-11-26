import rebootpy
import asyncio
import json
import os
import logging
import sys
from aiohttp import web

TAXI_ACCOUNT_NAME = "JarvisTaxi" 
AUTH_FILE = "device_auths.json"
API_PORT = 8080
BOT_OWNER_ID = "977589162213507073" 

SKIN_ID = "CID_701_Athena_Commando_M_BananaAgent"
EMOTE_ID = "EID_IceCream"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("TaxiService")

FORT_STATS_KEYS = [
    "fortitude", "offense", "resistance", "tech",
    "teamFortitude", "teamOffense", "teamResistance", "teamTech",
    "fortitude_Phoenix", "offense_Phoenix", "resistance_Phoenix", "tech_Phoenix",
    "teamFortitude_Phoenix", "teamOffense_Phoenix", "teamResistance_Phoenix", "teamTech_Phoenix"
]

def get_taxi_auth():
    if os.path.isfile(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                data = json.load(f)
                accounts = data.get(BOT_OWNER_ID, [])
                for acc in accounts:
                    if acc.get("account_name", "").lower() == TAXI_ACCOUNT_NAME.lower():
                        return {
                            "device_id": acc["device_id"],
                            "account_id": acc["account_id"],
                            "secret": acc["secret"]
                        }
        except Exception as e:
            log.error(f"Error reading auth file: {e}")
    return None

auth_data = get_taxi_auth()
if not auth_data:
    log.critical(f"❌ Auth not found for {TAXI_ACCOUNT_NAME}")
    sys.exit(1)

client = rebootpy.Client(
    auth=rebootpy.AdvancedAuth(prompt_device_code=False, **auth_data)
)

async def update_party_metadata():
    try:

        fort_stats = {key: 5000 for key in FORT_STATS_KEYS}
        metadata = {
            "Default:FORTStats_j": json.dumps({"FORTStats": fort_stats}),
            "Default:SubGame_s": "Campaign",
            "Default:Location_s": "PreLobby",
            "Default:HasCompletedSTWTutorial_b": "true",
            "Default:STWCompletedTutorial_b": "true",
            "Default:ActivityType_s": "STW",
            "Default:STWOwnership_b": "true",
            "Default:STWAccess_b": "true",
            "Default:STWPurchased_b": "true",
            "Default:STWEntitled_b": "true",
            "Default:STWProgress_j": json.dumps({
                "accountLevel": 310,
                "commanderLevel": 310,
                "collectionBookLevel": 500,
                "hasCompletedTutorial": True
            })
        }
        

        for key, value in metadata.items():
            client.party.meta.set_prop(key, value)
        try:
            await client.party.me.patch(updated=metadata)
            log.info("✅ Metadata Updated")
        except Exception as e:
            log.error(f"Metadata patch error: {e}")
        
        
    except Exception as e:
        log.error(f"Failed to update metadata: {e}")

async def handle_taxi_request(request):
    try:
        data = await request.json()
        target_username = data.get("username")
        
        if not target_username: 
            return web.Response(text="Missing username", status=400)

        target_username = target_username.strip()
        log.info(f"🚕 Taxi Request for: '{target_username}'")

        try:
            user = await client.fetch_user(target_username)
        except Exception as e:
            return web.Response(text=f"User '{target_username}' not found on Epic.", status=404)

        if not user:
            return web.Response(text="User not found.", status=404)

        friend = client.get_friend(user.id)
        
        if not friend:
            try:
                await user.add()
                log.info(f"Sent friend request to {user.display_name}")
                return web.Response(text=f"Sent friend request to **{user.display_name}**. Please accept it and run the command again!", status=200)
            except Exception as e:
                return web.Response(text=f"Failed to add friend: {e}", status=500)

        try:
            await friend.join_party()
            log.info(f"Joining {friend.display_name}...")
            return web.Response(text=f"✅ Joining **{friend.display_name}**! Please wait a moment...", status=200)
            
        except Exception as e:
            log.error(f"Join failed: {e}")
            return web.Response(text=f"Could not join **{friend.display_name}**. Is your party set to **Public**? ({e})", status=500)

    except Exception as e:
        log.error(f"API Error: {e}")
        return web.Response(text=f"Internal Error: {str(e)}", status=500)

async def start_server():
    app = web.Application()
    app.add_routes([web.post('/taxi', handle_taxi_request)])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', API_PORT)
    await site.start()
    log.info(f"🌐 API listening on http://127.0.0.1:{API_PORT}")


@client.event
async def event_ready():
    log.info(f"✅ Taxi Bot Online: {client.user.display_name}")
    client.set_presence(state="Waiting for Something...")
    await start_server()

@client.event
async def event_party_invite(invitation):
    try:
        await update_party_metadata()
        await invitation.accept()
    except Exception as e:
        log.error(f"Invite Error: {e}")

@client.event
async def event_party_invite(invitation):
    if client.party.member_count > 1:
        await invitation.decline()
        client.set_presence(state="Busy")
        return
    await update_party_metadata()
    await invitation.accept()


@client.event
async def event_party_member_join(member):

    if member.id == client.user.id:
        log.info("👋 I have joined the party!")
        try:
            # await update_party_metadata()

            await client.party.me.set_outfit(asset=SKIN_ID)
            await asyncio.sleep(0.5)
            await client.party.me.set_emote(asset=EMOTE_ID)
            log.info("✅ Set outfit and emote.")
            
        except Exception as e:
            log.error(f"Bot Join Error: {e}")

    else:
        log.info(f"👤 Member joined: {member.display_name}")
        await update_party_metadata()

if __name__ == "__main__":
    try:
        client.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.critical(f"Bot Crash: {e}")