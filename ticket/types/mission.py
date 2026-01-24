class MissionTicketType:
    type_name = "mission"

    def get_open_message(self, user, title: str) -> str:
        return (
            f"📌 **Ticket misji**\n"
            f"Użytkownik: {user.mention}\n"
            f"Tytuł: **{title}**\n\n"
            "Opisz proszę szczegóły misji korzystając ze wzoru, [klikając tu](https://docs.google.com/document/d/1E0HTNFTL6wVz0aZK6X4ydCPRGDwkW2M9_-5Zv_p1puo/edit?usp=sharing)."
        )

    def get_closed_message(self) -> str:
        return "Ticket misji został zamknięty."

    def get_reopened_message(self) -> str:
        return "Ticket misji został ponownie otwarty."
    
    async def on_ticket_created(self, bot, interaction, channel, category, title):
        await self.set_permissions_for_ticket_managers(channel, interaction.guild, bot.permissions.get("mission_tickets_managers", []))
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