"""
Game-night scheduler bot
—————————
• python bot.py post   – posts reaction-poll embeds
• python bot.py close  – tallies reactions → creates Discord Scheduled Event
• python bot.py demo   – 1-min end-to-end cycle (posts → waits → closes)
• python bot.py test   – offline logic test using dummy.yml (or custom file)
"""

from __future__ import annotations
import os, argparse, yaml, datetime as dt, asyncio, pytz, discord
from dateutil.parser import parse as dt_parse

try:                                           # ≥2.2
    from discord import ScheduledEventPrivacyLevel
except ImportError:                            # older forks
    from discord import PrivacyLevel as ScheduledEventPrivacyLevel

# ───────── CONFIG ─────────
CFG   = yaml.safe_load(open("config.yml", encoding="utf-8"))
TZ    = pytz.timezone(CFG["timezone"])
GID   = int(CFG["guild_id"])
CID   = int(CFG["channel_id"])

VC_NAME       = str(CFG["voice_channel"])
EVENT_HOURS   = int(CFG.get("event_hours", 3))
POLL_POST_STR = CFG["poll_post"]   # e.g. "Mon 09:00"
POLL_CLOSE_STR= CFG["poll_close"]  # e.g. "Wed 18:00"

COLOUR_TIME = int(CFG.get("embed_colour_time",  "#2ecc71").lstrip("#"), 16)
COLOUR_GAME = int(CFG.get("embed_colour_game",  "#3498db").lstrip("#"), 16)

DIGITS = ("1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.guild_scheduled_events = True
client  = discord.Client(intents=INTENTS)

_runner_cfg: dict[str,str|None] = {"mode":None,"file":None}

# ───────── HELPERS ─────────
def next_occurrence(text:str)->dt.datetime:
    t = dt_parse(text, fuzzy=True).replace(tzinfo=TZ)
    while t < dt.datetime.now(TZ): t += dt.timedelta(days=7)
    return t

def pick_winner(tv:dict[str,int], gv:dict[str,int]) -> tuple[str|None,str|None]:
    """Return (time, game) or (None,None) if no game meets threshold."""
    best_time = max(tv, key=tv.get)
    ordered   = sorted(gv.items(), key=lambda kv:(-kv[1],kv[0]))
    for name, votes in ordered:
        if votes >= CFG["games"][name]:
            return best_time, name
    return None, None

def cron_pretty(cron:str)->str:
    """'Mon 09:00' -> 'every **Mon** at **09:00**'"""
    dow, hm = cron.split()
    return f"every **{dow}** at **{hm}**"

# ───────── POST POLLS ─────────
async def create_polls() -> None:
    ch:discord.TextChannel = client.get_channel(CID)  # type: ignore
    if ch is None:
        print("channel not found"); return

    # header message
    await ch.send(
        f"📣 I will ask for availability {cron_pretty(POLL_POST_STR)} "
        f"and close voting {cron_pretty(POLL_CLOSE_STR)}.\n"
        f"React below to vote!"
    )

    # time embed
    e_time = discord.Embed(
        title="⏰ Choose a time",
        colour=COLOUR_TIME,
        description="\n".join(f"{DIGITS[i]}  `{s}`"
                              for i,s in enumerate(CFG["time_slots"]))
    )
    t_msg = await ch.send(embed=e_time)

    # game embed
    e_game = discord.Embed(
        title="🎲 Choose a game",
        colour=COLOUR_GAME,
        description="\n".join(
           f"{DIGITS[i]}  **{g}** (min {CFG['games'][g]})"
           for i,g in enumerate(CFG["games"])
        )
    )
    g_msg = await ch.send(embed=e_game)

    for i in range(len(CFG["time_slots"])): await t_msg.add_reaction(DIGITS[i])
    for i in range(len(CFG["games"])):       await g_msg.add_reaction(DIGITS[i])

    await t_msg.edit(content=f"<!--time:{t_msg.id}-->")
    await g_msg.edit(content=f"<!--game:{g_msg.id}-->")
    print("polls posted")

# ───────── CLOSE + SCHEDULE ─────────
async def close_and_schedule() -> None:
    ch:discord.TextChannel = client.get_channel(CID)  # type: ignore
    if ch is None: print("channel missing"); return

    t_msg=g_msg=None
    async for m in ch.history(limit=100):
        if m.content.startswith("<!--time:"): t_msg=m
        if m.content.startswith("<!--game:"): g_msg=m
        if t_msg and g_msg: break
    if not t_msg or not g_msg:
        await ch.send("⚠️ Couldn't find the polls to close."); return

    tv = {slot:(discord.utils.get(t_msg.reactions,emoji=DIGITS[i]).count-1
                if discord.utils.get(t_msg.reactions,emoji=DIGITS[i]) else 0)
          for i,slot in enumerate(CFG["time_slots"])}

    gv = {g:(discord.utils.get(g_msg.reactions,emoji=DIGITS[i]).count-1
             if discord.utils.get(g_msg.reactions,emoji=DIGITS[i]) else 0)
          for i,g in enumerate(CFG["games"])}

    time_win, game_win = pick_winner(tv, gv)

    if game_win is None:
        await ch.send("🚫 Not enough votes to meet any game's minimum players. "
                      "No event scheduled this week.")
        await t_msg.delete(); await g_msg.delete()
        return

    voters = gv[game_win]
    await ch.send(f"🎉 **{game_win}** wins with **{voters}** players "
                  f"at **{time_win}**!")

    guild = client.get_guild(GID)
    voice = discord.utils.get(guild.voice_channels, name=VC_NAME)
    if voice is None:
        await ch.send(f"⚠️ Voice channel '{VC_NAME}' not found.")
        return

    start = next_occurrence(time_win)
    await guild.create_scheduled_event(
        name=f"{game_win} — Weekly Game Night",
        start_time=start.astimezone(dt.timezone.utc),
        end_time=(start+dt.timedelta(hours=EVENT_HOURS)).astimezone(dt.timezone.utc),
        description=(f"Scheduled from weekly poll.\n"
                     f"**Time:** {time_win}\n**Game:** {game_win}\n"
                     f"**Players committed:** {voters}"),
        channel=voice,
        privacy_level=ScheduledEventPrivacyLevel.guild_only
    )
    await ch.send("📅 Event created and polls cleaned up.")
    await t_msg.delete(); await g_msg.delete()

# ───────── DEMO & OFFLINE TEST ─────────
async def demo() -> None:
    await create_polls(); await asyncio.sleep(60); await close_and_schedule()

def offline_test(path:str="dummy.yml") -> None:
    data=yaml.safe_load(open(path,"r",encoding="utf-8"))
    t,g = pick_winner(data["time_poll"], data["game_poll"])
    if g: print(f"[TEST] → {t}/{g}")
    else: print("[TEST] Not enough players.")

# ───────── READY ─────────
@client.event
async def on_ready() -> None:
    print(f"logged in as {client.user}")
    m=_runner_cfg["mode"]
    if m=="post":  await create_polls()
    elif m=="close": await close_and_schedule()
    elif m=="demo":  await demo()
    await client.close()

# ───────── CLI ─────────
def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=["post","close","demo","test"])
    p.add_argument("file",nargs="?",default="dummy.yml")
    a=p.parse_args()
    if a.mode=="test": offline_test(a.file); return
    _runner_cfg["mode"]=a.mode
    os.environ["BOT_TOKEN"] or (_:=(_ for _ in ()).throw(
        RuntimeError("BOT_TOKEN env var not set")))
    asyncio.run(client.start(os.environ["BOT_TOKEN"]))

if __name__=="__main__": main()
