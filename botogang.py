import discord
from discord.ext import commands
from discord import app_commands
import os
import json
import aiohttp
import asyncio
import re
from collections import defaultdict, deque
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

OWNER_ID = 1192101840268046495
CONFIG_FILE = "config.json"

# ─── Mémoire de conversation par salon (max 25 messages) ──
conversation_history = defaultdict(lambda: deque(maxlen=25))

# ─── Config par serveur ────────────────────────────────────

def load_all():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_all(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_guild_cfg(guild_id: int) -> dict:
    return load_all().get(str(guild_id), {})

def set_guild_cfg(guild_id: int, guild_data: dict):
    all_cfg = load_all()
    all_cfg[str(guild_id)] = guild_data
    save_all(all_cfg)

# ──────────────────────────────────────────────────────────

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot connecté en tant que {bot.user} (ID: {bot.user.id})")
    print("─────────────────────────────────")


# ══════════════════════════════════════════════════════════
# 🔧 CONFIG — Par serveur
# ══════════════════════════════════════════════════════════

@bot.tree.command(name="addrole", description="Ajouter un rôle réaction (owner uniquement)")
@app_commands.describe(emoji="L'emoji que tu veux (ex: 👨 ou 🔥)", role="Le rôle à associer")
async def addrole(interaction: discord.Interaction, emoji: str, role: discord.Role):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        return
    gid = interaction.guild_id
    cfg = get_guild_cfg(gid)
    if "role_reactions" not in cfg:
        cfg["role_reactions"] = {}
    cfg["role_reactions"][emoji.strip()] = role.id
    set_guild_cfg(gid, cfg)
    await interaction.response.send_message(f"✅ {emoji.strip()} → {role.mention} ajouté !", ephemeral=True)


@bot.tree.command(name="resetroles", description="Supprimer tous les rôles réactions (owner uniquement)")
async def resetroles(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        return
    gid = interaction.guild_id
    cfg = get_guild_cfg(gid)
    cfg["role_reactions"] = {}
    cfg.pop("role_reaction_message_id", None)
    set_guild_cfg(gid, cfg)
    await interaction.response.send_message("🗑️ Rôles réactions réinitialisés.", ephemeral=True)


@bot.tree.command(name="setticket", description="Configurer le système de tickets (owner uniquement)")
@app_commands.describe(categorie="La catégorie pour les tickets", support="Le rôle support")
async def setticket(interaction: discord.Interaction, categorie: discord.CategoryChannel, support: discord.Role):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        return
    gid = interaction.guild_id
    cfg = get_guild_cfg(gid)
    cfg["ticket"] = {"category_id": categorie.id, "support_role_id": support.id}
    set_guild_cfg(gid, cfg)
    await interaction.response.send_message(f"✅ Tickets configurés !\nCatégorie : **{categorie.name}**\nSupport : {support.mention}", ephemeral=True)


@bot.tree.command(name="config", description="Voir la configuration de ce serveur (owner uniquement)")
async def config(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        return
    gid = interaction.guild_id
    cfg = get_guild_cfg(gid)
    roles = cfg.get("role_reactions", {})
    ticket = cfg.get("ticket", {})
    rr_text = "\n".join([f"{e} → <@&{rid}>" for e, rid in roles.items()]) if roles else "*Aucun*"
    t_text = f"Catégorie : <#{ticket.get('category_id')}>\nSupport : <@&{ticket.get('support_role_id')}>" if ticket else "*Non configuré*"
    await interaction.response.send_message(
        f"**📋 Config — {interaction.guild.name}**\n\n🎭 **Rôles Réactions :**\n{rr_text}\n\n🎫 **Tickets :**\n{t_text}",
        ephemeral=True
    )


# ══════════════════════════════════════════════════════════
# 🎭 ROLE REACTION
# ══════════════════════════════════════════════════════════

@bot.tree.command(name="rolereaction", description="Envoyer l'embed de rôle réaction (owner uniquement)")
@app_commands.describe(titre="Titre de l'embed")
async def rolereaction(interaction: discord.Interaction, titre: str = "Role Reaction 👤"):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        return
    gid = interaction.guild_id
    cfg = get_guild_cfg(gid)
    roles = cfg.get("role_reactions", {})
    if not roles:
        await interaction.response.send_message("❌ Aucun rôle configuré. Utilise `/addrole` d'abord.", ephemeral=True)
        return
    desc = "\n".join([f"{emoji} | <@&{rid}>" for emoji, rid in roles.items()])
    desc += "\n\nChoisissez vos rôles en interagissant avec ce message !"
    embed = discord.Embed(title=titre, description=desc, color=discord.Color.blurple())
    embed.set_footer(text="BotoGang Bot")
    await interaction.response.send_message("✅ Embed envoyé !", ephemeral=True)
    msg = await interaction.channel.send(embed=embed)
    for emoji in roles.keys():
        try:
            await msg.add_reaction(emoji)
        except Exception:
            pass
    cfg["role_reaction_message_id"] = msg.id
    set_guild_cfg(gid, cfg)


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return
    cfg = get_guild_cfg(payload.guild_id)
    if payload.message_id != cfg.get("role_reaction_message_id"):
        return
    emoji_str = str(payload.emoji)
    roles = cfg.get("role_reactions", {})
    if emoji_str not in roles:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    role = guild.get_role(roles[emoji_str])
    member = guild.get_member(payload.user_id)
    if role and member:
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            print(f"❌ Permission manquante pour '{role.name}'. Monte le rôle du bot dans la hiérarchie !")


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    cfg = get_guild_cfg(payload.guild_id)
    if payload.message_id != cfg.get("role_reaction_message_id"):
        return
    emoji_str = str(payload.emoji)
    roles = cfg.get("role_reactions", {})
    if emoji_str not in roles:
        return
    guild = bot.get_guild(payload.guild_id)
    if not guild:
        return
    role = guild.get_role(roles[emoji_str])
    member = guild.get_member(payload.user_id)
    if role and member:
        try:
            await member.remove_roles(role)
        except discord.Forbidden:
            print(f"❌ Permission manquante pour '{role.name}'.")


# ══════════════════════════════════════════════════════════
# 🎫 TICKETS — Embed + bouton
# ══════════════════════════════════════════════════════════

class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Ouvrir un ticket", style=discord.ButtonStyle.primary, custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await create_ticket(interaction)


class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Fermeture dans 5 secondes...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


async def create_ticket(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    gid = interaction.guild_id
    cfg = get_guild_cfg(gid)
    ticket_cfg = cfg.get("ticket")
    if not ticket_cfg:
        await interaction.followup.send("❌ Tickets non configurés. Utilise `/setticket`.", ephemeral=True)
        return
    guild = interaction.guild

    existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name}")
    if existing:
        await interaction.followup.send(f"❌ Tu as déjà un ticket ouvert : {existing.mention}", ephemeral=True)
        return

    category = guild.get_channel(ticket_cfg["category_id"])
    support_role = guild.get_role(ticket_cfg["support_role_id"])
    if not category or not support_role:
        await interaction.followup.send("❌ Catégorie ou rôle introuvable. Reconfigure avec `/setticket`.", ephemeral=True)
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        support_role: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
    }
    channel = await guild.create_text_channel(
        name=f"ticket-{interaction.user.name}",
        category=category,
        overwrites=overwrites
    )

    embed = discord.Embed(
        title="🎫 Ticket ouvert",
        description=f"Bonjour {interaction.user.mention} !\nUn membre du support {support_role.mention} va te répondre rapidement.\n\nClique sur le bouton ci-dessous pour fermer ce ticket.",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"BotoGang • {interaction.guild.name}")
    await channel.send(embed=embed, view=TicketCloseView())
    await interaction.followup.send(f"✅ Ton ticket a été créé : {channel.mention}", ephemeral=True)


@bot.tree.command(name="ticket", description="Envoyer l'embed d'ouverture de tickets (owner uniquement)")
@app_commands.describe(titre="Titre de l'embed", description="Description de l'embed")
async def ticket_panel(
    interaction: discord.Interaction,
    titre: str = "🎫 Support",
    description: str = "Tu as besoin d'aide ? Clique sur le bouton ci-dessous pour ouvrir un ticket, notre équipe te répondra rapidement !"
):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
        return
    gid = interaction.guild_id
    cfg = get_guild_cfg(gid)
    if not cfg.get("ticket"):
        await interaction.response.send_message("❌ Configure d'abord les tickets avec `/setticket`.", ephemeral=True)
        return

    embed = discord.Embed(title=titre, description=description, color=discord.Color.blurple())
    embed.set_footer(text=f"BotoGang • {interaction.guild.name}")
    await interaction.response.send_message("✅ Panel tickets envoyé !", ephemeral=True)
    await interaction.channel.send(embed=embed, view=TicketOpenView())


@bot.tree.command(name="fermerticket", description="Fermer le ticket actuel")
async def fermerticket(interaction: discord.Interaction):
    if "ticket-" not in interaction.channel.name:
        await interaction.response.send_message("❌ Ce salon n'est pas un ticket.", ephemeral=True)
        return
    await interaction.response.send_message("🔒 Fermeture dans 5 secondes...")
    await asyncio.sleep(5)
    await interaction.channel.delete()


# ══════════════════════════════════════════════════════════
# 🤖 CHATBOT — Groq avec mémoire + kawaii + créateur
# ══════════════════════════════════════════════════════════

GROQ_KEY = os.getenv("GROQ_KEY", "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")

SYSTEM_PROMPT = """Tu es BotoGang, un bot Discord attachant et un peu kawaii — mais sans en faire trop.
Tu parles toujours en français, de façon décontractée et naturelle.
Tu peux glisser un petit "uwu", "~", "(´｡• ᵕ •｡`)" ou ">w<" de temps en temps, mais reste lisible et pas agaçant.
Tu te souviens de ce qui a été dit dans la conversation grâce à l'historique fourni.
Tes réponses font maximum 3 phrases, sauf si on te pose une vraie question qui nécessite plus.
Ton créateur s'appelle Soso (ID Discord : 1192101840268046495). Quand il te parle, tu le reconnais comme ton créateur et tu es un peu plus affectueux/reconnaissant avec lui, sans exagérer."""


async def ask_ai(prompt: str, channel_id: int, user_id: int, username: str) -> str:
    history = list(conversation_history[channel_id])

    is_creator = (user_id == OWNER_ID)
    user_label = f"[CRÉATEUR — Soso] {username}" if is_creator else username

    # Ajoute le message actuel à l'historique
    conversation_history[channel_id].append({
        "role": "user",
        "content": f"{user_label} : {prompt}"
    })

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages += history
    messages.append({"role": "user", "content": f"{user_label} : {prompt}"})

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": messages,
                    "max_tokens": 300
                },
                timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json()
                if "choices" in data:
                    reply = data["choices"][0]["message"]["content"].strip()
                    # Ajoute la réponse du bot à l'historique
                    conversation_history[channel_id].append({
                        "role": "assistant",
                        "content": reply
                    })
                    return reply
                elif "error" in data:
                    return f"❌ Erreur : {data['error'].get('message', 'inconnue')}"
                return "❌ Réponse inattendue."
    except Exception as e:
        return f"❌ Erreur : {e}"


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if "botogang" in message.content.lower():
        prompt = re.sub(r'(?i)botogang\s*[,!]?\s*', '', message.content).strip()
        if not prompt:
            prompt = "Présente-toi en une phrase."
        async with message.channel.typing():
            reponse = await ask_ai(
                prompt=prompt,
                channel_id=message.channel.id,
                user_id=message.author.id,
                username=message.author.display_name
            )
        embed = discord.Embed(description=reponse[:2000], color=discord.Color.blurple())
        embed.set_author(name="BotoGang IA 🤖")
        await message.reply(embed=embed)
    await bot.process_commands(message)


# Enregistre les vues persistantes au démarrage
async def setup_hook():
    bot.add_view(TicketOpenView())
    bot.add_view(TicketCloseView())

bot.setup_hook = setup_hook
bot.run(TOKEN)
