import discord
from discord.ext import commands
from discord import app_commands
from db.models import Users, Ranks, Attendance
import logging

logger = logging.getLogger("fogbot")

class RanksCog(commands.Cog):
    """Actions for rank promotions and other related."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot

    # TODO: Test this
    @commands.Cog.listener()
    async def on_attendance(self, user_ids: list[int]):
        if not hasattr(self.bot, "db") or self.bot.db is None:
            logger.warning("Database connection is not available.")
            return
        for user_id in user_ids:
            rows = await Users.get_user(self.bot.db, user_id)
            if rows is None:
                logger.warning(f"User with id {user_id} not found.")
                continue
            rank_id = rows[4]
            
            rows = await Attendance.get_by_user(self.bot.db, user_id)
            all_time_missions = rows[2]
            
            rows = await Ranks.get(self.bot.db, rank_id)
            if rows is None:
                logger.warning(f"Rank with id {rank_id} not found.")
                continue
            current_rank_id = rows[0]
            required_missions = rows[3]
            
            rows = await Ranks.get_next_rank(self.bot.db, required_missions)
            if rows is None:
                logger.warning(f"Next rank with required missions {required_missions} not found.")
                continue
            next_rank_id = rows[0]
            next_rank_name = rows[1]
            next_rank_role_id = rows[2]
            next_rank_required = rows[3]
            
            if all_time_missions >= next_rank_required:
                await Users.update_rank(self.bot.db, user_id, next_rank_id)
                guild = self.bot.get_guild(self.bot.guild_id)
                if guild is None:
                    continue
                member = guild.get_member(user_id)
                if member is None:
                    continue
                if current_rank_id is not None:
                    role = guild.get_role(current_rank_id)
                    if role is not None:
                        await member.remove_roles(role)
                if next_rank_role_id is not None:
                    role = guild.get_role(next_rank_role_id)
                    if role is not None:
                        await member.add_roles(role)
                        
                try:
                    await member.send(f"Gratulacje! Awansowałeś na rangę **{next_rank_name}**!")
                    logger.info(f"User with id {user_id} promoted to rank {next_rank_name}.")
                except Exception:
                    logger.warning(f"Failed to send DM to user with id {user_id}.")


async def setup(bot:commands.Bot):
    await bot.add_cog(RanksCog(bot))