# bot.py
# Main Discord bot for Goodgame Empire

import discord
from discord.ext import commands
import logging
import asyncio
import sys

# Windows consoles often default to cp1252; avoid crashing on emoji in prints.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import DISCORD_TOKEN, COMMAND_PREFIX, MESSAGE_TIMEOUT, DEFAULT_SERVER
from game_client import GameClient, GameClientError
from session_manager import SessionManager
from utils import (
    parse_options_input,
    format_options_output,
    get_server_code,
    get_server_name,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN not found in .env file!")
    exit(1)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)
bot.remove_command("help")

session_manager = SessionManager()


# === EVENT: on_ready ===
@bot.event
async def on_ready():
    logger.info(f"✅ Bot is online! Logged in as: {bot.user}")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing, name="Goodgame Empire | !help"
        )
    )
    print(f"\n{'='*50}\n✅ Bot is ready!\n📢 Logged in as: {bot.user}\n{'='*50}\n")


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)


# === COMMAND: !ping ===
@bot.command(name="ping")
async def ping_command(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: `{latency}ms`")


# === COMMAND: !help ===
@bot.command(name="help")
async def help_command(ctx):
    embed = discord.Embed(
        title="⭐ Goodgame Empire Bot Commands",
        description="Here are all the commands you can use:",
        color=discord.Color.blue(),
    )
    for cmd, desc in [
        ("!setup", "Start the account setup process"),
        ("!status", "Check your account status"),
        ("!castle", "Show your castle information"),
        ("!resources", "Show your resources"),
        ("!noble", "Show closest Noble Thieves castles"),
        ("!ping", "Check bot latency"),
        ("!about", "Information about this bot"),
        ("!cancel", "Cancel current setup session"),
    ]:
        embed.add_field(name=cmd, value=desc, inline=False)
    embed.set_footer(text="Made for Goodgame Empire players ❤️")
    await ctx.send(embed=embed)

# === COMMAND: !about ===
@bot.command(name="about")
async def about_command(ctx):
    embed = discord.Embed(
        title="ℹ️ About This Bot",
        description="A Discord bot for Goodgame Empire automation",
        color=discord.Color.gold(),
    )
    embed.add_field(
        name="📌 Features",
        value="• Account setup\n• Castle management\n• Resource tracking\n• Noble Thieves castle finder",
        inline=False,
    )
    embed.set_footer(text="Version 2.1.0")
    await ctx.send(embed=embed)


# === COMMAND: !setup ===
@bot.command(name="setup")
async def setup_command(ctx):
    if session_manager.session_exists(ctx.author.id):
        await ctx.send("⚠️ **You already have an active setup session!**")
        await ctx.send(f"Use `{COMMAND_PREFIX}cancel` to cancel it.")
        return

    session = session_manager.create_session(ctx.author.id)
    await ctx.send("🎮 **Welcome to Goodgame Empire Bot Setup!**")
    await ctx.send("I'll guide you through setting up your bot account.\n")
    await asyncio.sleep(1)
    await ask_username(ctx, session)


async def ask_username(ctx, session):
    session.step = 1
    await ctx.send("📝 **Step 1/4**: Enter your Goodgame Empire **Username**:")
    try:
        response = await bot.wait_for(
            "message",
            timeout=MESSAGE_TIMEOUT,
            check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
        )
        username = response.content.strip()
        if not username:
            await ctx.send("❌ Username cannot be empty!")
            await ask_username(ctx, session)
            return
        session.username = username
        await ctx.send(f"✅ Username set to: `{username}`")
        await asyncio.sleep(0.5)
        await ask_password(ctx, session)
    except asyncio.TimeoutError:
        await ctx.send("⏰ **Timeout!** Start over with `!setup`")
        session_manager.delete_session(ctx.author.id)


async def ask_password(ctx, session):
    session.step = 2
    await ctx.send("🔑 **Step 2/4**: Enter your game **Password**:")
    if ctx.guild is not None:
        await ctx.send(
            "⚠️ You're in a server channel, not a DM — I'll try to delete your password message right after reading it, but consider moving to a DM for safety."
        )
    try:
        response = await bot.wait_for(
            "message",
            timeout=MESSAGE_TIMEOUT,
            check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
        )
        password = response.content.strip()

        # FIX: best-effort delete of the message containing the plaintext
        # password. Only works in guild channels where the bot has
        # Manage Messages permission; DMs can't be deleted by the bot at all.
        try:
            await response.delete()
        except (discord.Forbidden, discord.NotFound, discord.HTTPException):
            pass

        if not password:
            await ctx.send("❌ Password cannot be empty!")
            await ask_password(ctx, session)
            return
        session.password = password
        await ctx.send("✅ Password received!")
        await asyncio.sleep(0.5)
        await ask_server(ctx, session)
    except asyncio.TimeoutError:
        await ctx.send("⏰ **Timeout!** Start over with `!setup`")
        session_manager.delete_session(ctx.author.id)


async def ask_server(ctx, session):
    session.step = 3
    await ctx.send("🌍 **Step 3/4**: Select your game server:")
    await ctx.send(
        "• `1` or `EG1` - Egypt 1 (**Default**)\n"
        "• `2` or `EG2` - Egypt 2\n"
        "• `3` or `US1` - USA 1\n"
        "• `4` or `EU1` - Europe 1\n\n"
        "Type the server code/number, or press Enter for default:"
    )
    try:
        response = await bot.wait_for(
            "message",
            timeout=MESSAGE_TIMEOUT,
            check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
        )
        server_input = response.content.strip()
        if not server_input:
            server_code = DEFAULT_SERVER
        else:
            server_code = get_server_code(server_input)
        session.server = server_code
        await ctx.send(f"✅ Server set to: `{get_server_name(server_code)}`")
        await asyncio.sleep(0.5)
        await ask_options(ctx, session)
    except asyncio.TimeoutError:
        await ctx.send("⏰ **Timeout!** Start over with `!setup`")
        session_manager.delete_session(ctx.author.id)


async def ask_options(ctx, session):
    session.step = 4
    await ctx.send("⚙️ **Step 4/4**: Configure bot options:")
    await ctx.send(
        "• `UseFeathers` (default: false)\n"
        "• `UseCoin` (default: true)\n"
        "• `UpgradeStormForts` (default: false)\n"
        "• `NobleThievesCastles` (default: true) - Find closest Noble Thieves\n\n"
        "**Example:** `UseCoin: false, UseFeathers: true, NobleThievesCastles: true`\n"
        "**Type `default` to use defaults**\n"
        "(Keys are not case-sensitive.)"
    )
    try:
        response = await bot.wait_for(
            "message",
            timeout=MESSAGE_TIMEOUT,
            check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
        )
        options_input = response.content.strip()

        if options_input.lower() == "default":
            from config import DEFAULT_OPTIONS

            session.options_settings = DEFAULT_OPTIONS.copy()
            unknown_keys = []
        else:
            session.options_settings, unknown_keys = parse_options_input(options_input)

        await ctx.send("✅ Options saved!")
        await ctx.send(format_options_output(session.options_settings))

        # FIX: previously, mistyped/unknown keys were silently dropped.
        if unknown_keys:
            await ctx.send(
                "⚠️ I didn't recognize these and ignored them: "
                + ", ".join(f"`{k}`" for k in unknown_keys)
            )

        await asyncio.sleep(1)
        await complete_setup(ctx, session)
    except asyncio.TimeoutError:
        await ctx.send("⏰ **Timeout!** Start over with `!setup`")
        session_manager.delete_session(ctx.author.id)


async def complete_setup(ctx, session):
    """Complete the setup process and connect to the game."""
    await ctx.send("\n⏳ **Connecting to Goodgame Empire...** Please wait.")

    try:
        game_client = GameClient(
            username=session.username, password=session.password, server=session.server
        )

        connected = await asyncio.to_thread(game_client.connect)

        # FIX: the password has done its job (handed to GameClient) —
        # drop it from the session immediately instead of keeping it
        # around in memory for the rest of the session's lifetime.
        session.clear_password()

        if not connected:
            await ctx.send("❌ **Failed to connect to the game.**")
            if game_client.last_error:
                await ctx.send(f"Reason: `{game_client.last_error}`")
            session_manager.delete_session(ctx.author.id)
            return

        settings = {
            "username": session.username,
            "server": session.server,
            "options": session.options_settings,
        }
        response = await asyncio.to_thread(game_client.setup_account, settings)

        if not response.get("success", False):
            await ctx.send(
                f"❌ **Setup failed:** {response.get('error', 'Unknown error')}"
            )
            game_client.disconnect()
            session_manager.delete_session(ctx.author.id)
            return

        session.game_client = game_client
        session.complete = True

        # FIX: honest status instead of a hardcoded "connected, here's your
        # fake castle/resources" embed. Socket-open vs actually-logged-in
        # are shown as what they are; game data is only shown if real.
        status_line = (
            "🟢 Logged in"
            if response.get("logged_in")
            else "🟡 Connected — waiting for login confirmation"
        )

        embed = discord.Embed(
            title="Account Setup",
            description=f"Session created for **{session.username}**",
            color=(
                discord.Color.green()
                if response.get("logged_in")
                else discord.Color.orange()
            ),
        )
        embed.add_field(
            name="📋 Account Details",
            value=f"**Username:** {session.username}\n**Server:** {get_server_name(session.server)}",
            inline=False,
        )
        embed.add_field(name="Status", value=status_line, inline=False)

        try:
            castle_info = game_client.get_castle_info()
            embed.add_field(
                name="🏰 Castle Info",
                value=f"**Name:** {castle_info.get('name', 'Unknown')}\n"
                f"**Level:** {castle_info.get('level', '—')}\n"
                f"**Points:** {castle_info.get('points', '—')}",
                inline=False,
            )
        except GameClientError:
            embed.add_field(
                name="🏰 Castle Info", value="Not available yet.", inline=False
            )

        try:
            resources = game_client.get_resources()
            embed.add_field(
                name="💰 Resources",
                value=f"🪵 Wood: {resources.get('wood', '—')}\n"
                f"🪨 Stone: {resources.get('stone', '—')}\n"
                f"⚙️ Iron: {resources.get('iron', '—')}\n"
                f"👑 Gold: {resources.get('gold', '—')}",
                inline=False,
            )
        except GameClientError:
            embed.add_field(
                name="💰 Resources", value="Not available yet.", inline=False
            )

        if session.options_settings.get("noble_thieves_castles", False):
            noble_castles = response.get("noble_thieves_castles", [])
            embed.add_field(
                name="🏴‍☠️ Closest Noble Thieves Castles",
                value=(
                    (
                        f"Found {len(noble_castles)} castles\n"
                        + "\n".join(f"• ID: {c}" for c in noble_castles[:5])
                    )
                    if noble_castles
                    else "Not available yet."
                ),
                inline=False,
            )

        if session.options_settings:
            lines = [
                f"• `{k.replace('_', ' ').title()}`: {'✅' if v else '❌'}"
                for k, v in session.options_settings.items()
            ]
            embed.add_field(name="⚙️ Options", value="\n".join(lines), inline=False)

        embed.set_footer(text="Setup complete.")
        await ctx.send(embed=embed)
        logger.info(f"Session created for: {session.username}")

    except Exception as e:
        logger.error(f"❌ Setup error: {str(e)}")
        await ctx.send(f"❌ **An error occurred:** {str(e)}")
        session_manager.delete_session(ctx.author.id)


# === COMMAND: !status ===
@bot.command(name="status")
async def status_command(ctx):
    session = session_manager.get_session(ctx.author.id)
    if not session:
        await ctx.send("ℹ️ **You don't have an active session.**")
        await ctx.send(f"Start with `{COMMAND_PREFIX}setup`")
        return

    embed = discord.Embed(title="📊 Account Status", color=discord.Color.blue())

    if session.complete:
        logged_in = bool(session.game_client and session.game_client.is_logged_in)
        embed.add_field(
            name="Status",
            value="🟢 Logged in" if logged_in else "🟡 Socket open, not logged in",
            inline=False,
        )
        embed.add_field(
            name="Username", value=session.username or "Not set", inline=True
        )
        embed.add_field(
            name="Server", value=get_server_name(session.server), inline=True
        )
        if session.game_client:
            embed.add_field(
                name="Player ID",
                value=session.game_client.player_id or "N/A",
                inline=True,
            )
        if session.options_settings:
            lines = [
                f"• `{k.replace('_', ' ').title()}`: {'✅' if v else '❌'}"
                for k, v in session.options_settings.items()
            ]
            embed.add_field(name="⚙️ Options", value="\n".join(lines), inline=False)
    else:
        step_names = {
            0: "Not started",
            1: "Username",
            2: "Password",
            3: "Server",
            4: "Options",
        }
        embed.add_field(name="Status", value="🟡 In Progress", inline=False)
        embed.add_field(
            name="Current Step",
            value=f"Step {session.step}/4 - {step_names.get(session.step, 'Unknown')}",
            inline=False,
        )
        embed.add_field(
            name="Username", value=session.username or "Not set", inline=True
        )
        embed.add_field(
            name="Server",
            value=get_server_name(session.server) if session.server else "Not set",
            inline=True,
        )

    await ctx.send(embed=embed)


# === COMMAND: !castle ===
@bot.command(name="castle")
async def castle_command(ctx):
    session = session_manager.get_session(ctx.author.id)
    if not session or not session.complete or not session.game_client:
        await ctx.send("❌ **Please run `!setup` first!**")
        return
    try:
        castle_info = await asyncio.to_thread(session.game_client.get_castle_info)
    except GameClientError as e:
        await ctx.send(f"❌ {e}")
        return
    embed = discord.Embed(title="🏰 Castle Information", color=discord.Color.gold())
    embed.add_field(name="Name", value=castle_info.get("name", "Unknown"), inline=True)
    embed.add_field(name="Level", value=castle_info.get("level", "—"), inline=True)
    embed.add_field(name="Points", value=castle_info.get("points", "—"), inline=True)
    await ctx.send(embed=embed)


# === COMMAND: !resources ===
@bot.command(name="resources")
async def resources_command(ctx):
    session = session_manager.get_session(ctx.author.id)
    if not session or not session.complete or not session.game_client:
        await ctx.send("❌ **Please run `!setup` first!**")
        return
    try:
        resources = await asyncio.to_thread(session.game_client.get_resources)
    except GameClientError as e:
        await ctx.send(f"❌ {e}")
        return
    embed = discord.Embed(title="💰 Resources", color=discord.Color.blue())
    embed.add_field(name="🪵 Wood", value=resources.get("wood", "—"), inline=True)
    embed.add_field(name="🪨 Stone", value=resources.get("stone", "—"), inline=True)
    embed.add_field(name="⚙️ Iron", value=resources.get("iron", "—"), inline=True)
    embed.add_field(name="👑 Gold", value=resources.get("gold", "—"), inline=True)
    await ctx.send(embed=embed)


# === COMMAND: !noble ===
@bot.command(name="noble")
async def noble_command(ctx):
    session = session_manager.get_session(ctx.author.id)
    if not session or not session.complete or not session.game_client:
        await ctx.send("❌ **Please run `!setup` first!**")
        return
    if not session.options_settings.get("noble_thieves_castles", False):
        await ctx.send("❌ **Noble Thieves Castles is not enabled in your settings!**")
        await ctx.send("Run `!setup` again and enable it.")
        return
    try:
        noble_castles = await asyncio.to_thread(
            session.game_client.get_noble_thieves_castles
        )
    except GameClientError as e:
        await ctx.send(f"❌ {e}")
        return
    embed = discord.Embed(
        title="🏴‍☠️ Closest Noble Thieves Castles", color=discord.Color.purple()
    )
    if noble_castles:
        embed.add_field(
            name="Castles Found",
            value=f"Found {len(noble_castles)} castles:\n"
            + "\n".join(f"• ID: `{c}`" for c in noble_castles[:10]),
            inline=False,
        )
    else:
        embed.add_field(
            name="No Castles Found",
            value="No Noble Thieves castles found nearby.",
            inline=False,
        )
    await ctx.send(embed=embed)


# === COMMAND: !cancel ===
@bot.command(name="cancel")
async def cancel_command(ctx):
    session = session_manager.get_session(ctx.author.id)
    if not session:
        await ctx.send("ℹ️ **You don't have an active session.**")
        return
    username = session.username or "Unknown"
    session_manager.delete_session(
        ctx.author.id
    )  # also disconnects game_client + clears password
    await ctx.send(f"✅ **Setup cancelled!** Session for `{username}` removed.")
    await ctx.send(f"Start over with `{COMMAND_PREFIX}setup`.")


# === ERROR HANDLING ===
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send(f"❌ **Command not found!** Use `{COMMAND_PREFIX}help`.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ **You don't have permission to use this command.**")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("❌ **I don't have permission to do that!**")
    else:
        logger.error(f"Command error: {str(error)}")
        await ctx.send(f"❌ **An error occurred:** {str(error)}")


# === RUN THE BOT ===
if __name__ == "__main__":
    try:
        print("\n🚀 Starting Goodgame Empire Bot...")
        bot.run(DISCORD_TOKEN)
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {str(e)}")
        print(f"\n❌ Error: {str(e)}")
