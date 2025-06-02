import os, argparse, yaml, datetime as dt, asyncio, zoneinfo
import discord
from dateutil.parser import parse as dt_parse

# ---------- CONFIG ----------
CFG = yaml.safe_load(open("config.yml", "r"))
TZ  = zoneinfo.ZoneInfo(CFG["timezone"])
GUILD_ID   = int(CFG["guild_id"])
CHANNEL_ID = int(CFG["channel_id"])

INTENTS = discord.Intents.default()
INTENTS.message_content = True
client  = discord.Client(intents=INTENTS)

# ---------- HELPERS ----------
def localise_slot(text):
    """Convert 'Tue 19:00' to the next datetime in the future (TZ-aware)."""
    now = dt.datetime.now(TZ)
    target = dt_parse(text, fuzzy=True).replace(tzinfo=TZ)
    while target < now:
        target += dt.timedelta(days=7)
    return target

async def create_polls():
    ch = client.get_channel(CHANNEL_ID)

    # 1) Time poll
    time_poll = await ch.create_poll(
        question="⏰ Choose a time for this week’s game night",
        answers=CFG["time_slots"],
        duration="2d"
    )
    # 2) Game poll
    game_poll = await ch.create_poll(
        question="🎲 Which game should we play?",
        answers=list(CFG["games"].keys()),
        duration="2d"
    )

    # Store the message IDs inside the poll footer for easy retrieval
    await time_poll.edit(content=f"{time_poll.content}\n<!--time:{time_poll.id}-->")
    await game_poll.edit(content=f"{game_poll.content}\n<!--game:{game_poll.id}-->")

async def close_polls_and_schedule():
    ch = client.get_channel(CHANNEL_ID)

    # Fetch last 100 messages to find our hidden IDs
    async for msg in ch.history(limit=100):
        if "<!--time:" in msg.content:
            time_msg = msg
        if "<!--game:" in msg.content:
            game_msg = msg
    # ----- tally votes -----
    best_time = max(time_msg.poll.answers, key=lambda a: a.votes).answer_text
    ordered_games = sorted(game_msg.poll.answers,
                           key=lambda a: a.votes, reverse=True)

    chosen_game = None
    for g in ordered_games:
        if g.votes >= CFG["games"][g.answer_text]:
            chosen_game = g.answer_text
            break
    if not chosen_game:                     # fallback if nothing meets threshold
        chosen_game = ordered_games[0].answer_text

    start_dt = localise_slot(best_time)
    guild    = client.get_guild(GUILD_ID)
    await guild.create_scheduled_event(
        name=f"{chosen_game} — Weekly Game Night",
        start_time=start_dt.astimezone(dt.timezone.utc),
        end_time=(start_dt + dt.timedelta(hours=3)).astimezone(dt.timezone.utc),
        description=f"Auto-scheduled from poll votes.\n\nTime: {best_time}\nGame: {chosen_game}",
        location="Voice Chat"
    )
    await ch.send(f"✅ **Scheduled:** {chosen_game} at {best_time} ({CFG['timezone']})")

    # Clean up
    await time_msg.delete()
    await game_msg.delete()

# ---------- CLI ----------
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["post", "close"])
    args = parser.parse_args()

    await client.login(os.getenv("BOT_TOKEN"))
    await client.connect(reconnect=False)   # needed to populate cache

    if args.mode == "post":
        await create_polls()
    else:
        await close_polls_and_schedule()

    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
