import rebootpy
import asyncio
import json
import os
import logging
import sys
from aiohttp import web
import random
from dotenv import load_dotenv

TAXI_ACCOUNT_NAME = "Klankeroo" 
AUTH_FILE = "device_auths.json"
API_PORT = 8080
load_dotenv()
BOT_OWNER_ID = os.getenv("BOT_ID")
MY_ACCOUNT_ID = os.getenv("MY_ACCOUNT")

SKIN_ID = "CID_A_189_Athena_Commando_M_Lavish_HUU31"
EMOTE_ID = ["EID_Wave", "EID_AmazingForever_Q68W0"]
EMOTE_ID_IDLE = ["EID_IgniteEgg_Jab", "EID_MikeCheck", "EID_YouBoreMe", "EID_ChairTime", "EID_Texting", "EID_HighActivity", "EID_Facepalm"]
BOT_MODE = "STW"
LEVEL_TO_SHOW = 420

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger("TaxiService")

FORT_STATS_KEYS = [
    "fortitude", "offense", "resistance", "tech",
    "teamFortitude", "teamOffense", "teamResistance", "teamTech",
    "fortitude_Phoenix", "offense_Phoenix", "resistance_Phoenix", "tech_Phoenix",
    "teamFortitude_Phoenix", "teamOffense_Phoenix", "teamResistance_Phoenix", "teamTech_Phoenix"
]

def get_id_by_name(target_name):
    if os.path.isfile(AUTH_FILE):
        try:
            with open(AUTH_FILE, 'r') as f:
                data = json.load(f)
                accounts = data.get(MY_ACCOUNT_ID, [])
                for acc in accounts:
                    if acc.get("account_name", "").lower() == target_name.lower():
                        return acc.get("account_id")
        except:
            pass
    return None

owner_id = get_id_by_name("Shrillkangaroo")

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
        raw_id = SKIN_ID
        prefixed_id = f"AthenaCharacter:{SKIN_ID}"

        mp_inner_data = {
            "ac": {"i": raw_id, "v": []}, "ab": {"i": "None", "v": []},                       
            "ag": {"i": "DefaultGlider", "v": []}, "ap": {"i": "DefaultPickaxe", "v": []},             
            "sb": {"i": "Sparks_Bass_Generic", "v": ["0"]}, "sg": {"i": "Sparks_Guitar_Generic", "v": ["0"]},   
            "sd": {"i": "Sparks_Drum_Generic", "v": ["0"]}, "sk": {"i": "Sparks_Keytar_Generic", "v": ["0"]},   
            "sm": {"i": "Sparks_Mic_Generic", "v": ["0"]}       
        }
        mp_wrapper = {"MpLoadout": {"d": json.dumps(mp_inner_data)}}

        athena_loadout = {
            "AthenaCosmeticLoadout": {
                "characterPrimaryAssetId": prefixed_id,
                "backpackDef": "None", "pickaxeDef": "AthenaPickaxe:DefaultPickaxe",
                "gliderDef": "AthenaGlider:DefaultGlider", "scratchpad": []
            }
        }
        if BOT_MODE == "STW":
            subgame = "Campaign"
            extra_meta = {
                "Default:FORTStats_j": json.dumps({"FORTStats": {k: 5000 for k in FORT_STATS_KEYS}}),
                "Default:STWProgress_j": json.dumps({"accountLevel": 310, "commanderLevel": 310, "hasCompletedTutorial": True})
            }
        else:
            subgame = "BattleRoyale"
            extra_meta = {}

        metadata = {
            "Default:SubGame_s": subgame, 
            "Default:Location_s": "PreLobby",
            
            "Default:AthenaCosmeticLoadout_j": json.dumps(athena_loadout),
            "Default:AthenaCosmeticLoadoutVariants_j": json.dumps({"AthenaCosmeticLoadoutVariants": {"vL": {"athenaCharacter": {"i": [], "vD": {}}}, "fT": False}}),
            "Default:MpLoadout_j": json.dumps(mp_wrapper),
            "Default:CampaignCosmeticLoadout_j": json.dumps(athena_loadout)
        }
        
        metadata.update(extra_meta)

        for key, value in metadata.items():
            client.party.meta.set_prop(key, value)
        await client.party.me.patch(updated=metadata)
        log.info(f"✅ Metadata Updated ({BOT_MODE} Mode)")
        
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


async def idle_task():
    while True:
        await asyncio.sleep(120)
        if client.party:
            try:
                await client.party.me.clear_emote()
                await asyncio.sleep(0.5)
                
                await client.party.me.set_emote(asset=random.choice(EMOTE_ID_IDLE))
                await asyncio.sleep(10)
                await client.party.me.clear_emote()
            except Exception as e:
                log.error(f"Idle emote error: {e}")


@client.event
async def event_ready():
    log.info(f"✅ Taxi Bot Online: {client.user.display_name}")
    client.set_presence(status="✅ Taxi Ready")
    await update_party_metadata()
    await start_server()
    await client.party.set_privacy(rebootpy.PartyPrivacy.PRIVATE)
    client.loop.create_task(idle_task())

@client.event
async def event_party_invite(invitation):
    #if invitation.sender.id == 
    if client.party.member_count > 1:
        await invitation.decline()
        return
    #await update_party_metadata()
    await invitation.accept()

@client.event
async def event_party_member_leave(member):
    if member.id == client.user.id:
        log.info("👋 I have left the party.")
        client.set_presence(status="✅ Taxi Ready")
        await client.party.set_privacy(rebootpy.PartyPrivacy.PRIVATE)
    else:
        if client.party.member_count == 1:
            client.set_presence(status="✅ Taxi Ready")
            await client.party.set_privacy(rebootpy.PartyPrivacy.PRIVATE)
        log.info(f"👤 Member left: {member.display_name}")
        #await update_party_metadata()

@client.event
async def event_party_member_join(member):
    if member.id == client.user.id:
        if client.party.member_count > 1:
            log.info("👋 I have joined the party!")
            try:
                await update_party_metadata()
                client.set_presence(status="❌ Taxi Busy")

                await asyncio.sleep(1)
                await client.party.me.set_emote(asset=random.choice(EMOTE_ID))
                log.info("✅ Emote Triggered.")
                await client.party.me.set_banner(
                    icon="BannerToken_033_S12_Skull", 
                    color="DefaultColor1", 
                    season_level=LEVEL_TO_SHOW
                )

                
            except Exception as e:
                log.error(f"Bot Join Error: {e}")
    else:
        log.info(f"👤 Member joined: {member.display_name}")

        await update_party_metadata()

last_leader_emote = None

@client.event
async def event_party_member_update(member):
    global last_leader_emote
    if member.id == client.user.id:
        return
    if member.id == owner_id:
        current_emote = member.emote
        if current_emote != last_leader_emote:
            if current_emote:
                log.info(f"💃 Mirroring The Goat: {current_emote}")
                await client.party.me.set_emote(asset=current_emote)
            else:
                log.info("The Goat stopped. Clearing emote.")
                await client.party.me.clear_emote()
            last_leader_emote = current_emote
        else:
            pass


if __name__ == "__main__":
    try:
        client.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        log.critical(f"Bot Crash: {e}")