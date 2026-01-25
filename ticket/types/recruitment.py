class RecruitmentTicketType:
    type_name = "recruitment"

    def get_open_message(self, user, title: str) -> str:
        return (
            f"🎱 **Ticket rekrutacji**\n"
            f"Użytkownik: {user.mention}\n\n"
            "Skorzystaj z poniższego wzoru, aby zgłosić się do rekrutacji:\n"
            "**Nick**:\n"
            "**Imię**:\n"
            "**Wiek**:\n"
            "**Ilość godzin w Arma 3 i/lub Arma Reforger:**\n"
            "**Doświadczenie z innych grup (z jakich?):**"
        )

    def get_closed_message(self) -> str:
        return "Ticket rekrutacji został zamknięty."

    def get_reopened_message(self) -> str:
        return "Ticket rekrutacji został ponownie otwarty."
    
    async def on_ticket_created(self, bot, interaction, channel, category, title):
        await self.set_permissions_for_ticket_managers(channel, interaction.guild, bot.permissions.get("recruiters", []))
        return
    
    # Set permissions for ticket managers
    async def set_permissions_for_ticket_managers(self, channel, guild, ticket_manager_ids):
        if ticket_manager_ids:
            for ticket_manager_role_id in ticket_manager_ids:
                ticket_manager_role = guild.get_role(ticket_manager_role_id)
                if ticket_manager_role:
                    await channel.set_permissions(
                        ticket_manager_role,
                        read_messages=True,
                        send_messages=True,
                        view_channel=True,
                    )