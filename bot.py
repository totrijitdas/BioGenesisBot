import discord
from discord.ext import commands
from discord.commands import Option
import json
import random
import os

# --- Configuration and Setup ---

# Define the intents your bot needs
intents = discord.Intents.default()
intents.members = True  # Required to see members joining
intents.message_content = True # Required for some potential future commands

bot = commands.Bot(command_prefix="/", intents=intents)

# Path for the data storage file
DATA_FILE = "data.json"
CONFIG_FILE = "config.json"

# --- Helper Functions for Data Storage ---

def load_config():
    """Loads configuration from config.json."""
    if not os.path.exists(CONFIG_FILE):
        print(f"ERROR: {CONFIG_FILE} not found! Please create it.")
        exit()
    with open(CONFIG_FILE, 'r') as f:
        return json.load(f)

def load_data():
    """Loads the ID data from the JSON file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            # Convert string keys back to integers for user IDs
            return {int(k): v for k, v in json.load(f).items()}
    return {}

def save_data(data):
    """Saves the ID data to the JSON file."""
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Load configuration and initial data
config = load_config()
BOT_TOKEN = config.get("BOT_TOKEN")
WELCOME_CHANNEL_ID = config.get("WELCOME_CHANNEL_ID")
ROLE_PREFIX = config.get("ROLE_PREFIX", "Member") # Defaults to "Member" if not set

user_ids = load_data()

# --- Core Logic ---

def get_new_id():
    """Generates a unique 3-digit ID."""
    all_possible_ids = set(range(1000))
    assigned_ids = {data['id'] for data in user_ids.values()}
    available_ids = list(all_possible_ids - assigned_ids)

    if not available_ids:
        return None  # No available IDs left

    new_id = random.choice(available_ids)
    return f"{new_id:03d}" # Formats the number as a 3-digit string (e.g., 5 -> "005")

async def assign_id_and_role(member):
    """Assigns a new ID and role to a member."""
    guild = member.guild
    
    # Rejoin Protection: Check if the user already has an ID
    if member.id in user_ids:
        user_data = user_ids[member.id]
        unique_id = user_data['id_str']
        role_name = f"{ROLE_PREFIX} #{unique_id}"
        
        # Check if the role still exists and assign it
        role = discord.utils.get(guild.roles, name=role_name)
        if role:
            await member.add_roles(role)
            print(f"Restored role '{role_name}' for rejoining member {member.name}.")
        else:
            # If role was deleted, recreate and assign it
            new_role = await guild.create_role(name=role_name)
            await member.add_roles(new_role)
            print(f"Re-created and assigned role '{role_name}' for rejoining member {member.name}.")
        return user_ids[member.id]['id_str']

    # New Member: Assign a new ID
    new_id_str = get_new_id()
    if new_id_str is None:
        print("Error: No available IDs left to assign.")
        # Optionally send a message to an admin channel
        return None

    role_name = f"{ROLE_PREFIX} #{new_id_str}"
    
    # Check if a role with this name already exists to avoid duplicates
    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        role = await guild.create_role(name=role_name)

    await member.add_roles(role)

    # Store the new user's data
    user_ids[member.id] = {
        "id": int(new_id_str),
        "id_str": new_id_str,
        "username": member.name
    }
    save_data(user_ids)
    print(f"Assigned ID {new_id_str} to new member {member.name}.")
    return new_id_str

# --- Bot Events ---

@bot.event
async def on_ready():
    """Event triggered when the bot is online and ready."""
    print(f'Logged in as {bot.user}')
    print('Bot is ready to assign IDs.')

@bot.event
async def on_member_join(member):
    """Event triggered when a new member joins the server."""
    print(f'{member.name} has joined the server.')
    
    assigned_id = await assign_id_and_role(member)
    
    if assigned_id and WELCOME_CHANNEL_ID:
        channel = bot.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=f"Welcome to the Server, {member.name}!",
                description=f"We're glad to have you here.\nYour unique ID is **#{assigned_id}**.",
                color=discord.Color.blue()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)
        else:
            print(f"Error: Welcome channel with ID {WELCOME_CHANNEL_ID} not found.")

# --- Slash Commands ---

@bot.slash_command(name="assign_existing", description="Assigns IDs to all existing members without one.")
@commands.has_permissions(administrator=True)
async def assign_existing(ctx):
    """Command to assign IDs to all existing members."""
    await ctx.defer()
    
    guild = ctx.guild
    assigned_count = 0
    
    for member in guild.members:
        if not member.bot and member.id not in user_ids:
            await assign_id_and_role(member)
            assigned_count += 1
            
    await ctx.followup.send(f"Process complete. Assigned IDs to {assigned_count} existing members.")

@bot.slash_command(name="getid", description="Displays the unique ID of a specific user.")
async def getid(ctx, user: discord.Member):
    """Command to get a specific user's ID."""
    if user.id in user_ids:
        unique_id = user_ids[user.id]['id_str']
        await ctx.respond(f"The ID for {user.mention} is **#{unique_id}**.")
    else:
        await ctx.respond(f"{user.mention} does not have an ID assigned yet.")

@bot.slash_command(name="refreshid", description="Admin Only: Re-assigns IDs to all members from scratch.")
@commands.has_permissions(administrator=True)
async def refreshid(ctx):
    """Command to wipe all IDs and reassign them."""
    await ctx.defer()
    
    guild = ctx.guild
    global user_ids
    
    # 1. Clear existing data
    user_ids.clear()
    
    # 2. Delete old roles
    for role in guild.roles:
        if role.name.startswith(f"{ROLE_PREFIX} #"):
            try:
                await role.delete(reason="Admin requested ID refresh.")
            except discord.Forbidden:
                print(f"Could not delete role {role.name} - insufficient permissions.")
            except discord.HTTPException as e:
                print(f"Failed to delete role {role.name}: {e}")

    # 3. Re-assign IDs to all non-bot members
    for member in guild.members:
        if not member.bot:
            await assign_id_and_role(member)
            
    await ctx.followup.send("All member IDs and roles have been refreshed.")

@bot.slash_command(name="listids", description="Lists all current ID assignments.")
@commands.has_permissions(administrator=True)
async def listids(ctx):
    """Command to list all assigned IDs."""
    await ctx.defer()
    
    if not user_ids:
        await ctx.followup.send("No IDs have been assigned yet.")
        return
        
    # Sort by ID number
    sorted_ids = sorted(user_ids.items(), key=lambda item: item[1]['id'])
    
    description_text = ""
    for user_id, data in sorted_ids:
        user = ctx.guild.get_member(user_id)
        mention = user.mention if user else f"User left (ID: {user_id})"
        description_text += f"**#{data['id_str']}**: {mention}\n"
        
    # Discord embed descriptions have a character limit of 4096
    if len(description_text) > 4096:
        await ctx.followup.send("The list is too long to display in a single message. This feature could be expanded to support pagination.")
        return
        
    embed = discord.Embed(title="Assigned Member IDs", description=description_text, color=discord.Color.green())
    await ctx.followup.send(embed=embed)

# Error Handling for commands
@bot.event
async def on_application_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.respond("You do not have the required permissions to run this command.", ephemeral=True)
    else:
        # For other errors, log them and inform the user
        print(f"An error occurred: {error}")
        await ctx.respond("An unexpected error occurred. Please check the bot's console.", ephemeral=True)

# --- Run the Bot ---
if not BOT_TOKEN:
    print("Error: BOT_TOKEN not found in config.json. Please set it.")
else:
    print("Configuration loaded. Attempting to connect to Discord...") # <--- ADD THIS LINE
    bot.run(BOT_TOKEN)