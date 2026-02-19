import discord


class ProposalTicketType:
    type_name = "proposal"

    def get_open_message(self, user, title: str, bot) -> str:
        message = bot.ticket_system.get("ticket_messages", {}).get("proposal", "")
        if message:
            return message.format(mention=user.mention, name=user.name, id=user.id, guild=user.guild.name, display_name=user.display_name, title=title)
        return (
            f"💡 **Ticket propozycji**\n"
            f"Użytkownik: {user.mention}\n"
            f"Tytuł: **{title}**\n\n"
            "Opisz proszę swoją propozycję. Pierwsza wiadomość w tym kanale będzie traktowana jako opis propozycji."
        )

    def get_closed_message(self) -> str:
        return "Ticket propozycji został zamknięty."

    def get_reopened_message(self) -> str:
        return "Ticket propozycji został ponownie otwarty."
    
    async def customize_open_view(self, view, bot, interaction, channel, category, title):
        view.add_item(ProposalForwardButton(bot, channel.id, title))




class ProposalForwardButton(discord.ui.Button):
        def __init__(self, bot, channel_id, title):
            super().__init__(
                label="Przekaż propozycję do głosowania",
                style=discord.ButtonStyle.primary,
                custom_id=f"ticket_proposal_forward_{channel_id}",
            )
            self.bot = bot
            self.channel_id = channel_id
            self.title = title
            self.proposal_channel_id = bot.channels.get("proposals_channel_id")

        async def callback(self, interaction: discord.Interaction):
            if not interaction.user.guild_permissions.administrator or interaction.channel.permissions_for(interaction.user).manage_messages is False:
                await interaction.response.send_message("Nie masz uprawnień do przekazywania propozycji.", ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            
            channel = self.bot.get_channel(self.channel_id)
            description_text = None

            if channel is not None:
                msgs = [m async for m in channel.history(limit=2, oldest_first=True)]
                if len(msgs) >= 2:
                    description_text = msgs[1].content
                    description_author = msgs[1].author
                    

            if not description_text or not description_text.strip():
                description_text = "Brak opisu."
                
            embed = discord.Embed(
                title="Nowa propozycja do głosowania",
                description=f"**Tytuł:** {self.title}\n**Użytkownik:** {description_author.mention}\n\n",
                color=discord.Color.green(),
            )
            
            embed.add_field(
                name="Opis",
                value=description_text[:1024],
                inline=False,
            )
            
            proposal_channel = self.bot.get_channel(self.proposal_channel_id)
            if proposal_channel is None:
                proposal_channel = await self.bot.fetch_channel(self.proposal_channel_id)

            message = await proposal_channel.send(embed=embed)
            await message.add_reaction("👍")
            await message.add_reaction("👎")
            
            await interaction.followup.send("Propozycja przekazana.", ephemeral=True)

