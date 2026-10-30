import asyncio
import os
import random
import sqlite3
import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
from datetime import datetime, timezone

# Настройка интентов
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ==================== БАЗА ДАННЫХ (SQLite) ====================
db = sqlite3.connect("database.db")
cursor = db.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    guild_id INTEGER,
    xp INTEGER DEFAULT 0,
    coins INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_daily TEXT DEFAULT '2000-01-01'
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS inventory (
    user_id INTEGER,
    item_name TEXT
)
""")
db.commit()

def get_user(user_id):
    cursor.execute("SELECT xp, coins, level, last_daily FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO users (user_id, xp, coins, level, last_daily) VALUES (?, 0, 0, 1, '2000-01-01')", (user_id,))
        db.commit()
        return [0, 0, 1, "2000-01-01"]
    return row

def update_user(user_id, xp, coins, level, last_daily):
    cursor.execute("UPDATE users SET xp = ?, coins = ?, level = ?, last_daily = ? WHERE user_id = ?", (xp, coins, level, last_daily, user_id))
    db.commit()

# ==================== НАСТРОЙКИ МАГАЗИНОВ И РОЛЕЙ ====================
ROLE_SHOP_1_ID = 1562879763390009344  
ROLE_SHOP_2_ID = 1562878394855850094  

SHOPS_DATA = {
    "shop1": {
        "title": "⚓ Морской Флот — Магазин званий",
        "role_id": ROLE_SHOP_1_ID,
        "items": {
            "Seaman": {"price": 100, "type": "role", "role_id": 1562879834273746954},
            "Petty Officer": {"price": 250, "type": "role", "role_id": 1562879940288970843},
            "Lieutenant": {"price": 500, "type": "role", "role_id": 1562879979602186250},
            "Captain": {"price": 850, "type": "role", "role_id": 1562880007913742506},
            "Commodore": {"price": 1300, "type": "role", "role_id": 1562880037848490106},
            "Rear Admiral": {"price": 1850, "type": "role", "role_id": 1562880062242685011},
            "Vice Admiral": {"price": 2500, "type": "role", "role_id": 1562880092865298533},
            "Admiral": {"price": 3300, "type": "role", "role_id": 1562880118462881996},
            "Fleet Admiral": {"price": 4500, "type": "role", "role_id": 1562880151736291428},
        }
    },
    "shop2": {
        "title": "🏴‍☠️ Пиратский Путь — Магазин рангов",
        "role_id": ROLE_SHOP_2_ID,
        "items": {
            "Pirate": {"price": 100, "type": "role", "role_id": 1249791630022807617},
            "Corsair": {"price": 250, "type": "role", "role_id": 1562878579015159888},
            "Pirate Specialist": {"price": 500, "type": "role", "role_id": 1562878644785778809},
            "First Mate": {"price": 850, "type": "role", "role_id": 1562878667506323526},
            "Captain": {"price": 1300, "type": "role", "role_id": 1562878710795731034},
            "Supernova": {"price": 1850, "type": "role", "role_id": 1562878756463579267},
            "Commander": {"price": 2500, "type": "role", "role_id": 156288899061530644}, 
            "Shichibukai": {"price": 3300, "type": "role", "role_id": 1562878788742807634},
            "Yonko": {"price": 4500, "type": "role", "role_id": 1562878819428474940},
        }
    }
}

# ==================== ИНТЕРАКТИВНЫЕ КНОПКИ МАГАЗИНА ====================
class ShopSelectView(View):
    def __init__(self, member: discord.Member):
        super().__init__(timeout=60)
        self.member = member

    @discord.ui.button(label="⚓ Магазин Морского Флота", style=discord.ButtonStyle.primary)
    async def shop_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        shop = SHOPS_DATA["shop1"]
        if shop["role_id"] not in [r.id for r in self.member.roles]:
            return await interaction.response.send_message("❌ У вас нет роли **#1** для доступа к этому магазину!", ephemeral=True)
        await interaction.response.edit_message(embed=create_shop_embed("shop1"), view=ShopItemView(self.member, "shop1"))

    @discord.ui.button(label="🏴‍☠️ Магазин Пиратов", style=discord.ButtonStyle.danger)
    async def shop_two(self, interaction: discord.Interaction, button: discord.ui.Button):
        shop = SHOPS_DATA["shop2"]
        if shop["role_id"] not in [r.id for r in self.member.roles]:
            return await interaction.response.send_message("❌ У вас нет роли **#2** для доступа к этому магазину!", ephemeral=True)
        await interaction.response.edit_message(embed=create_shop_embed("shop2"), view=ShopItemView(self.member, "shop2"))


class ShopItemView(View):
    def __init__(self, member: discord.Member, shop_key: str):
        super().__init__(timeout=60)
        self.member = member
        self.shop_key = shop_key
        shop = SHOPS_DATA[shop_key]

        for item_name, data in shop["items"].items():
            btn = Button(label=f"{item_name} ({data['price']} 🪙)", style=discord.ButtonStyle.secondary)
            btn.callback = self.create_callback(item_name, data)
            self.add_item(btn)

    def create_callback(self, item_name, data):
        async def item_callback(interaction: discord.Interaction):
            if interaction.user.id != self.member.id:
                return await interaction.response.send_message("Это не ваше меню покупки!", ephemeral=True)

            xp, coins, level, daily = get_user(self.member.id)
            if coins < data["price"]:
                return await interaction.response.send_message(f"❌ Недостаточно монет! У вас: {coins} 🪙, нужно: {data['price']} 🪙.", ephemeral=True)

            # Списание монет
            coins -= data["price"]
            update_user(self.member.id, xp, coins, level, daily)

            # Выдача роли
            if data["type"] == "role":
                role = interaction.guild.get_role(data["role_id"])
                if role:
                    await self.member.add_roles(role)

            await interaction.response.send_message(f"✅ Вы успешно приобрели ранг/звание **{item_name}**!", ephemeral=True)
        return item_callback

def create_shop_embed(shop_key):
    shop = SHOPS_DATA[shop_key]
    embed = discord.Embed(
        title=shop["title"],
        description="Выберите звание/ранг для покупки с помощью кнопок ниже:",
        color=discord.Color.gold()
    )
    for name, data in shop["items"].items():
        embed.add_field(name=name, value=f"Цена: **{data['price']} 🪙**", inline=False)
    return embed

# ==================== СОБЫТИЯ И АКТИВНОСТЬ ====================
@bot.event
async def on_ready():
    print(f"Бот {bot.user} успешно запущен!")
    await bot.tree.sync()  
    print("Слэш-команды синхронизированы.")
    check_voice_activity.start()

@bot.event
async def on_message(message):
    if message.author.bot: return

    xp, coins, level, daily = get_user(message.author.id)
    xp += 20
    coins += random.randint(1, 4)

    next_lvl_xp = level * 100
    if xp >= next_lvl_xp:
        level += 1
        xp -= next_lvl_xp
        await message.channel.send(f"🎉 Поздравляем, {message.author.mention}, вы повысили уровень до **{level}**!")

    update_user(message.author.id, xp, coins, level, daily)
    await bot.process_commands(message)

@tasks.loop(seconds=60)
async def check_voice_activity():
    for guild in bot.guilds:
        for channel in guild.voice_channels:
            members = [m for m in channel.members if not m.bot]
            if len(members) >= 2:
                for member in members:
                    xp, coins, level, daily = get_user(member.id)
                    xp += 6 
                    coins += 1
                    update_user(member.id, xp, coins, level, daily)

# ==================== СЛЭШ КОМАНДЫ (SLASH COMMANDS) ====================

@bot.tree.command(name="shop", description="Открыть доступные магазины")
async def slash_shop(interaction: discord.Interaction):
    view = ShopSelectView(interaction.user)
    embed = discord.Embed(
        title="🛒 Выбор фракции / Магазина",
        description="Выберите магазин, соответствующий вашей роли (доступен только владельцам ролей):",
        color=discord.Color.blurple()
    )
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="balance", description="Посмотреть свой баланс или баланс другого участника")
async def slash_balance(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    xp, coins, level, daily = get_user(member.id)

    embed = discord.Embed(title=f"👤 Профиль: {member.display_name}", color=discord.Color.green())
    embed.add_field(name="✨ Уровень", value=str(level), inline=True)
    embed.add_field(name="⭐ Опыт (XP)", value=f"{xp} / {level * 100}", inline=True)
    embed.add_field(name="🪙 Монеты", value=str(coins), inline=True)
    embed.set_thumbnail(url=member.display_avatar.url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="daily", description="Получить ежедневный бонус")
async def slash_daily(interaction: discord.Interaction):
    xp, coins, level, last_daily_str = get_user(interaction.user.id)
    
    last_daily = datetime.fromisoformat(last_daily_str)
    now = datetime.now(timezone.utc)

    if (now - last_daily).total_seconds() < 86400:
        remaining = int(86400 - (now - last_daily).total_seconds())
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        return await interaction.response.send_message(f"⏳ Вы уже получали ежедневный бонус! Ждите еще **{hours} ч. {minutes} мин.**", ephemeral=True)

    bonus_coins = 200
    bonus_xp = 150
    coins += bonus_coins
    xp += bonus_xp

    update_user(interaction.user.id, xp, coins, level, now.isoformat())
    await interaction.response.send_message(f"🎁 {interaction.user.mention}, получен бонус: **{bonus_coins} 🪙** и **{bonus_xp} XP**!")

# Запуск бота
bot.run("MTU2NTU4NDg5NTg2MDgwMTYyNw.GxzouR.mvzKAMf3MvP4n2EgkRps1nFLguqABRvQVWZ0O8")