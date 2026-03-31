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
        
    async def _rank_up(self, user_id: int, current_rank, next_rank): # rank structure: id, name, role_id, required_missions
        next_rank_id = next_rank[0]
        current_rank_role_id = current_rank[2]
        next_rank_role_id = next_rank[2]
        next_rank_name = next_rank[1]
        
        await Users.update_rank(self.bot.db, user_id, next_rank_id)
        guild = self.bot.get_guild(self.bot.guild_id)
        if guild is None:
            return
        member = guild.get_member(user_id)
        if member is None:
            return

        role = guild.get_role(current_rank_role_id)
        if role is not None:
            await member.remove_roles(role)

        role = guild.get_role(next_rank_role_id)
        if role is not None:
            await member.add_roles(role)
        
        if current_rank_role_id == self.bot.roles["recruit_role_id"] and self.bot.roles["operator_role_id"] != 0:
            operator_role = guild.get_role(self.bot.roles["operator_role_id"])
            if operator_role is not None:
                await member.add_roles(operator_role)

        try:
            await member.send(f"Gratulacje! Awansowałeś na rangę **{next_rank_name}**!")
            logger.info(f"User with id {user_id} promoted to rank {next_rank_name}.")
        except Exception:
            logger.warning(f"Failed to send DM to user with id {user_id}.")
        

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
            
            max_missions = await Ranks.get_max_rank(self.bot.db)[3]
            
            if all_time_missions >= max_missions:
                continue
            
            current_rank = await Ranks.get(self.bot.db, rank_id)
            if current_rank is None:
                logger.warning(f"Rank with id {rank_id} not found.")
                continue
            current_rank_required_missions = current_rank[3]
            
            next_rank = await Ranks.get_next_rank(self.bot.db, current_rank_required_missions)
            if next_rank is None:
                logger.warning(f"Next rank with required missions {current_rank_required_missions} not found.")
                continue
            next_rank_required_missions = next_rank[3]
            
            if all_time_missions >= next_rank_required_missions:
                await self._rank_up(user_id, current_rank, next_rank)


async def setup(bot:commands.Bot):
    await bot.add_cog(RanksCog(bot))