import discord
from discord.ext import commands
from discord import app_commands
from db.models import Users
import logging
import random
from discord.ext import tasks

logger = logging.getLogger("fogbot")

MAXEXP = 55100
MAXLVL = 100
MAXEXPGAIN = 25
MINEXPGAIN = 10

class Level(commands.Cog):
    """User leveling system."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.users_experience_cache = {}
        self.cooldown_cache = {}
        
    _calculate_experience = staticmethod(lambda level: int(5 * (level ** 2) + (50 * level) + 100))
    _calculate_level = staticmethod(lambda experience: int((-50 + (20 * experience + 500)** 0.5) / 10))
    _check_level_up = staticmethod(lambda current_exp, new_exp: Level._calculate_level(new_exp) > Level._calculate_level(current_exp))

    async def _get_cached_experience(self, user_id: int) -> int:
        if user_id in self.users_experience_cache:
            logger.debug(f"Experience for user {user_id} fetched from cache.")
            return self.users_experience_cache[user_id]
        user = await Users.get_user(self.bot.db, user_id)
        exp = user[3] if user is not None else 0
        self.users_experience_cache[user_id] = exp
        logger.debug(f"Experience for user {user_id} fetched from database.")
        return exp
        

    async def _user_level_up(self, user_id: int, level: int) -> None:
        logger.info(f"User {user_id} leveled up to {level}!")
        await Users.update_level(self.bot.db, user_id, level)
        
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if user is not None:
                await user.send(f"Gratulacje, awansowałeś na poziom **{level}**! 🎉")
        except (discord.Forbidden, discord.HTTPException, discord.NotFound) as e:
            logger.warning(f"Could not DM user {user_id} about level up: {e}")

    # Periodically flush cached experience to the database
    @tasks.loop(minutes=1)
    async def _flush_experience_cache(self) -> None:
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validation of db access
            return
        if not self.users_experience_cache:
            return
        logger.debug(f"Flushing experience cache {self.users_experience_cache} to database...")

        last_flushed = getattr(self, "_last_flushed_exp", None)
        if last_flushed is None:
            last_flushed = {}
            setattr(self, "_last_flushed_exp", last_flushed)

        for user_id, exp in list(self.users_experience_cache.items()):
            prev_exp = last_flushed.get(user_id)

            if prev_exp is None:
                user = await Users.get_user(self.bot.db, user_id)
                prev_exp = user[3] if user is not None else 0

            if exp == prev_exp:
                continue

            await Users.update_experience(self.bot.db, user_id, exp)

            if self._check_level_up(prev_exp, exp):
                new_level = min(self._calculate_level(exp), MAXLVL)
                await self._user_level_up(user_id, new_level)

            last_flushed[user_id] = exp

    @_flush_experience_cache.before_loop
    async def _before_flush_experience_cache(self) -> None:
        await self.bot.wait_until_ready()

    async def cog_load(self) -> None:
        self._flush_experience_cache.start()

    async def cog_unload(self) -> None:
        self._flush_experience_cache.cancel()
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None:
            return
        if message.guild.id != self.bot.guild_id:
            return
        if message.author.bot:
            return
        
        current_time = message.created_at.timestamp()
        user_id = message.author.id
        if user_id in self.cooldown_cache:
            last_message_time = self.cooldown_cache[user_id]
            if current_time - last_message_time < 60:
                return
        self.cooldown_cache[user_id] = current_time
        
        current_exp = await self._get_cached_experience(user_id)
        gained_exp = random.randint(MINEXPGAIN, MAXEXPGAIN)
        new_exp = min(current_exp + gained_exp, MAXEXP)
        self.users_experience_cache[user_id] = new_exp
        
    # /level
    @app_commands.command(
        name="level",
        description="Sprawdź swój poziom i doświadczenie.",
        extras={"category": "Poziomy"}
    )
    async def level(self, interaction: discord.Interaction, uzytkownik: discord.User = None):
        user_id = uzytkownik.id if uzytkownik else interaction.user.id
        current_exp = await self._get_cached_experience(user_id)
        current_level = self._calculate_level(current_exp)
        next_level = current_level + 1
        exp_for_next_level = self._calculate_experience(next_level)
        exp_needed = exp_for_next_level - current_exp
        leaderboard = await Users.get_leaderboard(self.bot.db)
        rank = 1
        for idx, (uid, _, _, _) in enumerate(leaderboard, start=1):
            if uid == user_id:
                rank = idx
                break

        embed = discord.Embed(
            title=f"Poziom użytkownika {uzytkownik.name if uzytkownik else interaction.user.name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Aktualny poziom", value=str(current_level), inline=False)
        embed.add_field(name="Doświadczenie", value=f"{current_exp} XP", inline=False)
        if current_level < MAXLVL:
            embed.add_field(name="Do następnego poziomu", value=f"{exp_needed} XP", inline=False)
        else:
            embed.add_field(name="Do następnego poziomu", value="Osiągnięto maksymalny poziom!", inline=False)
        embed.add_field(name="Poziom w rankingu", value=f"#{rank}", inline=False)

        await interaction.response.send_message(embed=embed)
        
    # /leaderboard
    @app_commands.command(
        name="leaderboard",
        description="Pokaż ranking poziomów użytkowników.",
        extras={"category": "Poziomy"}
    )
    @app_commands.describe(limit="Liczba użytkowników do wyświetlenia w rankingu (domyślnie 10).")
    async def leaderboard(self, interaction: discord.Interaction, limit: int = 10):
        leaderboard = await Users.get_leaderboard(self.bot.db, limit)
        embed = discord.Embed(
            title="Ranking poziomów użytkowników",
            color=discord.Color.green()
        )
        for rank, (_, username, level, experience) in enumerate(leaderboard, start=1):
            embed.add_field(
                name=f"#{rank} - {username}",
                value=f"Poziom: {level}, Doświadczenie: {experience} XP",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

async def setup(bot:commands.Bot):
    await bot.add_cog(Level(bot))