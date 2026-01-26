import discord
from discord.ext import commands
import logging
from os import getenv

logger = logging.getLogger("fogbot")
debug = getenv("DEBUG") == "True"


class Security(commands.Cog):
    """Security actions"""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.deleting_roles = False
        
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.guild is None:
            return
        if before.guild.id != self.bot.guild_id:
            return
        if before.roles == after.roles:
            return
        if self.deleting_roles:
            return
        
        if debug:
            logger.debug(f"Member update detected for {after} ({after.id})")
        
        # ===== Remove unauthorized roles from candidates and other group =====
        candidate_role_id = self.bot.roles.get("candidate_role_id")
        other_group_role_id = self.bot.roles.get("other_group_role_id")
        whitelist_role_ids = self.bot.roles.get("unverified_roles_whitelist", [])
        whitelist_role_ids.append(candidate_role_id)
        whitelist_role_ids.append(other_group_role_id)
        
        if debug:
            logger.debug(f"Candidate role ID: {candidate_role_id}")
            logger.debug(f"Other group role ID: {other_group_role_id}")
            logger.debug(f"Whitelist role IDs: {whitelist_role_ids}")

        # Only enforce for candidates and other group members
        for role in before.roles:
            if role.id == candidate_role_id or role.id == other_group_role_id:
                break
        else:
            return
        
        if debug:
            logger.debug(f"Enforcing role whitelist for {after} ({after.id})")

        roles_to_remove = []
        for role in after.roles:
            # skip @everyone
            if role.is_default():
                continue
            if role.id not in whitelist_role_ids:
                roles_to_remove.append(role)
                
        if debug:
            logger.debug(f"Roles to remove from {after} ({after.id}): {[role.name for role in roles_to_remove]}")

        self.deleting_roles = True
        for role in roles_to_remove:
            try:
                await after.remove_roles(role, reason="Candidate role whitelist enforcement")
            except discord.Forbidden:
                continue

            try:
                await after.send(f"Rola {role.name} jest tylko dostępna dla członków grupy.")
            except discord.Forbidden:
                pass
        self.deleting_roles = False

async def setup(bot:commands.Bot):
    await bot.add_cog(Security(bot))