# bot.py
# Main Discord bot for Goodgame Empire

import discord
from discord.ext import commands
import logging
import asyncio

# Import our modules
from config import DISCORD_TOKEN, COMMAND_PREFIX, MESSAGE_TIMEOUT, DEFAULT_SERVER
from game_client import GameClient
from session_manager import SessionManager
from utils import (
    parse_options_input,
    format_options_output,
    get_server_code,
    get_server_name,
)

# Setup logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Check token
if not DISCORD_TOKEN:
    logger.error("❌ DISCORD_TOKEN not found in .env file!")
    exit(1)

# Setup bot intents
intents = discord.Intents.default()
intents.message_content = True

# Create bot instance
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

# Remove default help command
bot.remove_command("help")

# Initialize session manager
session_manager = SessionManager()


# === EVENT: on_ready ===
@bot.event
async def on_ready():
    """Triggered when the bot successfully connects to Discord"""
    logger.info(f"✅ Bot is online! Logged in as: {bot.user}")
    logger.info(f"Bot ID: {bot.user.id}")

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.playing, name="Goodgame Empire | !help"
        )
    )

    print(f"\n{'='*50}")
    print(f"✅ Bot is ready!")
    print(f"📢 Logged in as: {bot.user}")
    print(f"{'='*50}\n")


# === EVENT: on_message ===
@bot.event
async def on_message(message):
    """Handle all incoming messages"""
    if message.author == bot.user:
        return
    await bot.process_commands(message)


# === COMMAND: !ping ===
@bot.command(name="ping")
async def ping_command(ctx):
    """Check bot's response time"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"🏓 Pong! Latency: `{latency}ms`")


# === COMMAND: !help ===
@bot.command(name="help")
async def help_command(ctx):
    """Show all available commands"""
    embed = discord.Embed(
        title="⭐ Goodgame Empire Bot Commands",
        description="Here are all the commands you can use:",
        color=discord.Color.blue(),
    )

    commands_list = [
        ("!setup", "Start the account setup process"),
        ("!status", "Check your account status"),
        ("!castle", "Show your castle information"),
        ("!resources", "Show your resources"),
        ("!noble", "Show closest Noble Thieves castles"),
        ("!ping", "Check bot latency"),
        ("!about", "Information about this bot"),
        ("!cancel", "Cancel current setup session"),
    ]

    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)

    embed.set_footer(text="Made for Goodgame Empire players ❤️")
    await ctx.send(embed=embed)


# === COMMAND: !about ===
@bot.command(name="about")
async def about_command(ctx):
    """Show information about the bot"""
    embed = discord.Embed(
        title="ℹ️ About This Bot",
        description="A Discord bot for Goodgame Empire automation",
        color=discord.Color.gold(),
    )

    embed.add_field(
        name="📌 Features",
        value="• Account setup automation\n"
        "• Castle management\n"
        "• Resource tracking\n"
        "• Noble Thieves castle finder\n"
        "• WebSocket connection",
        inline=False,
    )

    embed.add_field(
        name="🛠️ Built With",
        value="• Python 3.x\n" "• discord.py\n" "• WebSocket + Requests",
        inline=False,
    )

    embed.set_footer(text="Version 2.0.0")
    await ctx.send(embed=embed)


# === COMMAND: !setup ===
@bot.command(name="setup")
async def setup_command(ctx):
    """Start the account setup process"""
    if session_manager.session_exists(ctx.author.id):
        await ctx.send("⚠️ **You already have an active setup session!**")
        await ctx.send(f"Use `{COMMAND_PREFIX}cancel` to cancel it.")
        return

    session = session_manager.create_session(ctx.author.id)

    await ctx.send("🎮 **Welcome to Goodgame Empire Bot Setup!**")
    await ctx.send("I'll guide you through setting up your bot account.\n")
    await asyncio.sleep(1)

    await ask_username(ctx, session)


# === Helper: ask_username ===
async def ask_username(ctx, session):
    """Ask user for their game username"""
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


# === Helper: ask_password ===
async def ask_password(ctx, session):
    """Ask user for their game password"""
    session.step = 2

    await ctx.send("🔑 **Step 2/4**: Enter your game **Password**:")

    try:
        response = await bot.wait_for(
            "message",
            timeout=MESSAGE_TIMEOUT,
            check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
        )

        password = response.content.strip()

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


# === Helper: ask_server ===
async def ask_server(ctx, session):
    """Ask user for their game server (EG1 is default)"""
    session.step = 3

    await ctx.send("🌍 **Step 3/4**: Select your game server:")
    await ctx.send("• `1` or `EG1` - Egypt 1 (**Default**)")
    await ctx.send("• `2` or `EG2` - Egypt 2")
    await ctx.send("• `3` or `US1` - USA 1")
    await ctx.send("• `4` or `EU1` - Europe 1")
    await ctx.send("\nType the server code/number, or press Enter for default:")

    try:
        response = await bot.wait_for(
            "message",
            timeout=MESSAGE_TIMEOUT,
            check=lambda m: m.author == ctx.author and m.channel == ctx.channel,
        )

        server_input = response.content.strip()

        if not server_input:
            server_code = DEFAULT_SERVER
            server_name = get_server_name(server_code)
            await ctx.send(f"✅ Using default server: `{server_name}`")
        else:
            server_code = get_server_code(server_input)
            server_name = get_server_name(server_code)
            await ctx.send(f"✅ Server set to: `{server_name}`")

        session.server = server_code
        await asyncio.sleep(0.5)

        await ask_options(ctx, session)

    except asyncio.TimeoutError:
        await ctx.send("⏰ **Timeout!** Start over with `!setup`")
        session_manager.delete_session(ctx.author.id)


# === Helper: ask_options ===
async def ask_options(ctx, session):
    """Ask user for bot options"""
    session.step = 4

    await ctx.send("⚙️ **Step 4/4**: Configure bot options:")
    await ctx.send("• `UseFeathers` (default: false)")
    await ctx.send("• `UseCoin` (default: true)")
    await ctx.send("• `UpgradeStormForts` (default: false)")
    await ctx.send(
        "• `NobleThievesCastles` (default: true) - Find closest Noble Thieves"
    )
    await ctx.send(
        "\n**Example:** `UseCoin: false, UseFeathers: true, NobleThievesCastles: true`"
    )
    await ctx.send("**Type `default` to use defaults**\n")

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
            await ctx.send("✅ Using default options:")
            await ctx.send(format_options_output(session.options_settings))
        else:
            session.options_settings = parse_options_input(options_input)
            await ctx.send("✅ Options saved!")
            await ctx.send(format_options_output(session.options_settings))

        await asyncio.sleep(1)
        await complete_setup(ctx, session)

    except asyncio.TimeoutError:
        await ctx.send("⏰ **Timeout!** Start over with `!setup`")
        session_manager.delete_session(ctx.author.id)


# === Helper: complete_setup ===
async def complete_setup(ctx, session):
    """Complete the setup process and connect to the game"""
    await ctx.send("\n⏳ **Connecting to Goodgame Empire...** Please wait.")

    try:
        game_client = GameClient(
            username=session.username, password=session.password, server=session.server
        )

        if not game_client.connect():
            await ctx.send("❌ **Failed to connect to the game!**")
            await ctx.send("Please check your username and password.")
            session_manager.delete_session(ctx.author.id)
            return

        settings = {
            "username": session.username,
            "server": session.server,
            "options": session.options_settings,
        }

        response = game_client.setup_account(settings)

        if not response.get("success", False):
            await ctx.send(
                f"❌ **Setup failed:** {response.get('error', 'Unknown error')}"
            )
            game_client.disconnect()
            session_manager.delete_session(ctx.author.id)
            return

        session.game_client = game_client
        session.complete = True

        castle_info = game_client.get_castle_info()
        resources = game_client.get_resources()

        embed = discord.Embed(
            title="✅ Account Connected!",
            description=f"Successfully connected to **{session.username}**",
            color=discord.Color.green(),
        )

        embed.add_field(
            name="📋 Account Details",
            value=f"**Username:** {session.username}\n"
            f"**Server:** {get_server_name(session.server)}\n"
            f"**Plugin:** Attack Berimond (Kingdom)",
            inline=False,
        )

        embed.add_field(
            name="🏰 Castle Info",
            value=f"**Name:** {castle_info.get('name', 'Unknown')}\n"
            f"**Level:** {castle_info.get('level', 1)}\n"
            f"**Points:** {castle_info.get('points', 0)}",
            inline=False,
        )

        embed.add_field(
            name="💰 Resources",
            value=f"🪵 Wood: {resources.get('wood', 0)}\n"
            f"🪨 Stone: {resources.get('stone', 0)}\n"
            f"⚙️ Iron: {resources.get('iron', 0)}\n"
            f"👑 Gold: {resources.get('gold', 0)}",
            inline=False,
        )

        # Noble Thieves Castles
        if session.options_settings.get("noble_thieves_castles", False):
            noble_castles = response.get("noble_thieves_castles", [])
            if noble_castles:
                embed.add_field(
                    name="🏴‍☠️ Closest Noble Thieves Castles",
                    value=f"Found {len(noble_castles)} castles\n"
                    + "\n".join([f"• ID: {c}" for c in noble_castles[:5]]),
                    inline=False,
                )
            else:
                embed.add_field(
                    name="🏴‍☠️ Noble Thieves Castles",
                    value="Searching for closest...",
                    inline=False,
                )

        # Options
        if session.options_settings:
            lines = []
            for key, value in session.options_settings.items():
                status = "✅" if value else "❌"
                display = key.replace("_", " ").title()
                lines.append(f"• `{display}`: {status}")
            embed.add_field(name="⚙️ Options", value="\n".join(lines), inline=False)

        embed.add_field(name="🟢 Status", value="Connected and Running", inline=False)
        embed.set_footer(text="Bot is now running! 🚀")

        await ctx.send(embed=embed)

        if game_client.send_chat_message("🤖 Bot online and ready!"):
            await ctx.send("💬 Test chat message sent to alliance chat!")

        await ctx.send(f"📩 **[{session.username}]** Connected successfully!")

        logger.info(f"✅ Account connected for: {session.username}")

    except Exception as e:
        logger.error(f"❌ Setup error: {str(e)}")
        await ctx.send(f"❌ **An error occurred:** {str(e)}")
        session_manager.delete_session(ctx.author.id)


# === COMMAND: !status ===
@bot.command(name="status")
async def status_command(ctx):
    """Check your account status"""
    session = session_manager.get_session(ctx.author.id)

    if not session:
        await ctx.send("ℹ️ **You don't have an active session.**")
        await ctx.send(f"Start with `{COMMAND_PREFIX}setup`")
        return

    embed = discord.Embed(title="📊 Account Status", color=discord.Color.blue())

    if session.complete:
        embed.add_field(name="Status", value="✅ Connected", inline=False)
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
            lines = []
            for key, value in session.options_settings.items():
                status = "✅" if value else "❌"
                display = key.replace("_", " ").title()
                lines.append(f"• `{display}`: {status}")
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
    """Show your castle information"""
    session = session_manager.get_session(ctx.author.id)

    if not session or not session.complete:
        await ctx.send("❌ **Please run `!setup` first!**")
        return

    if not session.game_client:
        await ctx.send("❌ **Not connected to the game!**")
        return

    castle_info = session.game_client.get_castle_info()

    embed = discord.Embed(title="🏰 Castle Information", color=discord.Color.gold())

    embed.add_field(name="Name", value=castle_info.get("name", "Unknown"), inline=True)
    embed.add_field(name="Level", value=castle_info.get("level", 1), inline=True)
    embed.add_field(name="Points", value=castle_info.get("points", 0), inline=True)

    await ctx.send(embed=embed)


# === COMMAND: !resources ===
@bot.command(name="resources")
async def resources_command(ctx):
    """Show your resources"""
    session = session_manager.get_session(ctx.author.id)

    if not session or not session.complete:
        await ctx.send("❌ **Please run `!setup` first!**")
        return

    if not session.game_client:
        await ctx.send("❌ **Not connected to the game!**")
        return

    resources = session.game_client.get_resources()

    embed = discord.Embed(title="💰 Resources", color=discord.Color.blue())

    embed.add_field(name="🪵 Wood", value=resources.get("wood", 0), inline=True)
    embed.add_field(name="🪨 Stone", value=resources.get("stone", 0), inline=True)
    embed.add_field(name="⚙️ Iron", value=resources.get("iron", 0), inline=True)
    embed.add_field(name="👑 Gold", value=resources.get("gold", 0), inline=True)

    await ctx.send(embed=embed)


# === COMMAND: !noble ===
@bot.command(name="noble")
async def noble_command(ctx):
    """Show closest Noble Thieves castles"""
    session = session_manager.get_session(ctx.author.id)

    if not session or not session.complete:
        await ctx.send("❌ **Please run `!setup` first!**")
        return

    if not session.game_client:
        await ctx.send("❌ **Not connected to the game!**")
        return

    if not session.options_settings.get("noble_thieves_castles", False):
        await ctx.send("❌ **Noble Thieves Castles is not enabled in your settings!**")
        await ctx.send("Run `!setup` again and enable it.")
        return

    noble_castles = session.game_client.get_noble_thieves_castles()

    embed = discord.Embed(
        title="🏴‍☠️ Closest Noble Thieves Castles", color=discord.Color.purple()
    )

    if noble_castles:
        embed.add_field(
            name="Castles Found",
            value=f"Found {len(noble_castles)} castles:\n"
            + "\n".join([f"• ID: `{c}`" for c in noble_castles[:10]]),
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
    """Cancel your current setup session"""
    session = session_manager.get_session(ctx.author.id)

    if not session:
        await ctx.send("ℹ️ **You don't have an active session.**")
        return

    if session.game_client:
        session.game_client.disconnect()

    username = session.username or "Unknown"
    session_manager.delete_session(ctx.author.id)

    await ctx.send(f"✅ **Setup cancelled!** Session for `{username}` removed.")
    await ctx.send(f"Start over with `{COMMAND_PREFIX}setup`.")


# === ERROR HANDLING ===
@bot.event
async def on_command_error(ctx, error):
    """Handle command errors gracefully"""
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
