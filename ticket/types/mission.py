class MissionTicketType:
    type_name = "mission"

    def get_open_message(self, user, title: str, bot) -> str:
        message = bot.ticket_system.get("ticket_messages", {}).get("mission", "")
        if message:
            return message.format(mention=user.mention, name=user.name, id=user.id, guild=user.guild.name, display_name=user.display_name, title=title)
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
    
    def get_ticket_managers_ids(self, bot):
        return bot.permissions.get("mission_tickets_managers", [])
    
    async def on_ticket_created(self, bot, interaction, channel, category, title):
        return
