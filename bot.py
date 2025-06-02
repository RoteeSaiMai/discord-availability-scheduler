import os, argparse, yaml, datetime as dt, asyncio, zoneinfo
import discord
import pytz
from dateutil.parser import parse as dt_parse

# ---------- CONFIG ----------
CFG = yaml.safe_load(open("config.yml", "r", encoding="utf-8"))
TZ  = pytz.timezone(CFG["timezone"])
GUILD_ID   = int(CFG["guild_id"])
CHANNEL_ID = int(CFG["channel_id"])

INTENTS = discord.Intents.default()
INTENTS.message_content = True
client  = discord.Client(intents=INTENTS)

# ---------- PURE-LOGIC HELPERS ----------
def localise_slot(text: str) -> dt.datetime:
    """Convert 'Tue 19:00' into the next occurrence in the future (TZ-aware)."""
    now = dt.datetime.now(TZ)
    target = dt_parse(text, fuzzy=True).replace(tzinfo=TZ)
    while target < now:
        target += dt.timedelta(days=7)
    return target

def pick_winner(time_votes: dict[str, int],
                game_votes: dict[str, int]) -> tuple[str, str]:
    """Return (best_time, chosen_game) based purely on vote dicts."""
    best_time = max(time_votes, key=time_votes.get)

    ordered = sorted(game_votes.items(), key=lambda kv: (-kv[1], kv[0]))  # votes ↓ then A-Z
    for name, votes in ordered:
        if votes >= CFG["games"].get(name, 0):
            return best_time, name

    # fallback if no game meets its threshold
    return best_time, ordered[0][0]

# ---------- DISCORD ACTIONS ----------
async def create_polls():
    ch = client.get_channel(CHANNEL_ID)

    time_poll = await ch.create_poll(
        question="⏰ Choose a time for this week’s game night",
        answers=CFG["time_slots"],
        duration="2d"
    )
    game_poll = await ch.create_poll(
        question="🎲 Which game should we play?",
        answers=list(CFG["games"].keys()),
        duration="2d"
    )

    # Save message IDs in hidden HTML comments for easy retrieval
    await time_poll.edit(content=f"{time_poll.content}\n<!--time:{time_poll.id}-->")
    await game_poll.edit(content=f"{game_poll.content}\n<!--game:{game_poll.id}-->")

async def close_polls_and_schedule():
    ch = client.get_channel(CHANNEL_ID)

    time_msg = game_msg = None
    async for msg in ch.history(limit=100):
        if "<!--time:" in msg.content:
            time_msg = msg
        if "<!--game:" in msg.content:
            game_msg = msg
    if not time_msg or not game_msg:
        await ch.send("⚠️ Could not find active polls.")
        return

    best_time = max(time_msg.poll.answers, key=lambda a: a.votes).answer_text
    game_votes = {a.answer_text: a.votes for a in game_msg.poll.answers}
    chosen_time, chosen_game = pick_winner(
        {best_time: 999},  # not used further
        game_votes
    )

    start_dt = localise_slot(chosen_time)
    guild    = client.get_guild(GUILD_ID)
    await guild.create_scheduled_event(
        name=f"{chosen_game} — Weekly Game Night",
        start_time=start_dt.astimezone(dt.timezone.utc),
        end_time=(start_dt + dt.timedelta(hours=3)).astimezone(dt.timezone.utc),
        description=f"Auto-scheduled from poll votes.\nTime: {chosen_time}\nGame: {chosen_game}",
        location="Voice Chat"
    )
    await ch.send(f"✅ **Scheduled:** {chosen_game} at {chosen_time} ({CFG['timezone']})")

    # tidy up
    await time_msg.delete()
    await game_msg.delete()

# ---------- TEST / DEMO UTILITIES ----------
async def demo_cycle():
    """Post polls that expire in 3 min, then auto-schedule."""
    await create_polls()
    await asyncio.sleep(240)  # 4 minutes
    await close_polls_and_schedule()

def offline_test(path: str = "dummy.yml"):
    raw = yaml.safe_load(open(path, "r", encoding="utf-8"))
    best_t, game = pick_winner(raw["time_poll"], raw["game_poll"])
    print(f"[TEST] Chosen time  => {best_t}")
    print(f"[TEST] Chosen game  => {game}")

# ---------- CLI ----------
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode",
                        choices=["post", "close", "demo", "test"],
                        help="Task to run")
    parser.add_argument("file", nargs="?", default="dummy.yml",
                        help="YAML file for 'test' mode (default: dummy.yml)")
    args = parser.parse_args()

    # Offline logic unit-test
    if args.mode == "test":
        offline_test(args.file)
        return

    # Everything else needs a live Discord connection
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable not set.")

    await client.login(token)
    await client.connect(reconnect=False)   # populate cache

    if args.mode == "post":
        await create_polls()
    elif args.mode == "close":
        await close_polls_and_schedule()
    elif args.mode == "demo":
        await demo_cycle()

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
