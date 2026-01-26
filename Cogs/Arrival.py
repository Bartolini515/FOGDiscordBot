import discord
from discord.ext import commands
from discord import app_commands
import logging
from db.models import Users, Blacklist
from datetime import datetime

logger = logging.getLogger("fogbot")

class Arrival(commands.Cog):
    """Actions for new arrival members."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot
        self.log_channel_id = self.bot.channels.get("log_channel_id")
        self.invites = {}


    # Don't implement until new structure is ready
    # TODO: Implement dm welcome message to explain next steps
    # TODO: Assign start roles
    # TODO: Invite tracking
    # TODO: Log arrivals to specified channel
    
    @commands.Cog.listener()
    async def on_ready(self):
        invites = await self.bot.get_guild(self.bot.guild_id).invites()
        self.invites = {invite.code: invite.uses for invite in invites}
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild is None:
            return
        if member.guild.id != self.bot.guild_id:
            return
        
        invites_before = self.invites.copy()
        invites_after = await self.bot.get_guild(self.bot.guild_id).invites()
        used_invite = None
        for invite in invites_after:
            if invite.code in invites_before:
                if invite.uses > invites_before[invite.code]:
                    used_invite = invite
                    break
            else:
                if invite.uses > 0:
                    used_invite = invite
                    break
        self.invites = {invite.code: invite.uses for invite in invites_after}
        
        if not hasattr(self.bot, "db") or self.bot.db is None: # Validate db connection
            return
        
        # Check if user is blacklisted
        if await Blacklist.is_blacklisted(self.bot.db, member.id):
            logger.info(f"Zablokowany użytkownik {member} ({member.id}) próbował dołączyć do serwera.")
            
            rows = await Blacklist.get(self.bot.db, member.id)
            if not rows:
                logger.error(f"Nie udało się pobrać powodu blokady dla użytkownika {member} ({member.id})")
                return
            reason = rows[1]
            end_at = rows[2]
            added_at = rows[3]
            time_left = "Nieskończony"
            if end_at:
                end_date = datetime.fromisoformat(end_at)
                delta = end_date - datetime.now()
                time_left = str(delta.days) if delta.days > 0 else "-1"
            if self.log_channel_id:
                log_channel = member.guild.get_channel(self.log_channel_id)
                if log_channel and isinstance(log_channel, discord.TextChannel):
                    embed = discord.Embed(
                        title="Zablokowany użytkownik próbował dołączyć",
                        description=f"{member.mention} ({member.id}) próbował dołączyć do serwera, ale znajduje się na blacklist.",
                        color=discord.Color.red()
                    )
                    embed.set_thumbnail(url=member.display_avatar.url)
                    embed.add_field(name="Powód blokady", value=reason, inline=False)
                    embed.add_field(name="Data dodania do blacklisty", value=added_at.split(" ")[0], inline=False)
                    embed.add_field(name="Data końca blokady", value=end_at.split(" ")[0] if end_at else "Nieskończony", inline=False)
                    embed.add_field(name="Pozostały czas blokady (dni)", value=time_left, inline=False)
                    embed.add_field(name="Zaproszony przez", value=used_invite.inviter.mention if used_invite and used_invite.inviter else "Nieznany", inline=False)
                    await log_channel.send(embed=embed)
            
            await member.send(f"Nie możesz dołączyć do FOG, znajdujesz się na blackliście.\nPowód: {reason}.\nDodany: {added_at}.\nKoniec blokady: {end_at if end_at else 'Nieskończony'}.\nPozostały czas (dni): {time_left}.")
            await member.kick(reason=f"Użytkownik znajduje się na blacklist. Powód: {reason}")
            return
        
        # Welcome message via DM
        try:
            # TODO: Update welcome message content
            dm_channel = await member.create_dm()
            welcome_message = (
                f"Witaj na serwerze FOG, {member.mention}!\n\n"
                "Cieszymy się, że do nas dołączyłeś. Przeczytaj poniższe instrukcje które pomogą Ci zacząć.\n\n"
                "- Zapoznaj się z regulaminem grupy który to znajdziesz pod tym linkiem: https://docs.google.com/document/d/1a8v9An-_wGI2StIZwWovKk0gOyM-wjEv2JaGPy8VobE/edit?usp=sharing\n"
                "- Jeżeli chcesz zostać pełnoprawnym członkiem grupy, sprawdź kanał #informacje gdzie dowiesz się wszystkich potrzebnych informacji na ten temat.\n"
                "- Jeżeli jesteś z innej grupy i masz propozycję współpracy, skontaktuj się z imperatorem lub innymi członkami sztabu.\n"
            )
            await dm_channel.send(welcome_message)
        except Exception as e:
            logger.error(f"Nie udało się wysłać wiadomości powitalnej do {member} ({member.id}): {e}")
        
        # Add user in database
        await Users.add_user(self.bot.db, member.id, member.name)
        
        # Log to channel
        if self.log_channel_id:
            log_channel = member.guild.get_channel(self.log_channel_id)
            if log_channel and isinstance(log_channel, discord.TextChannel):
                embed = discord.Embed(
                    title="Nowy członek dołączył",
                    description=f"{member.mention} ({member.id}) dołączył do serwera.",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.add_field(name="Dołączył", value=member.joined_at.strftime("%Y-%m-%d %H:%M:%S"), inline=False)
                embed.add_field(name="Zaproszony przez", value=used_invite.inviter.mention if used_invite and used_invite.inviter else "Nieznany", inline=False)
                embed.add_field(name="Całkowita liczba członków", value=str(member.guild.member_count), inline=False)
                await log_channel.send(embed=embed)
        

async def setup(bot:commands.Bot):
    await bot.add_cog(Arrival(bot))