class CustomTicketType:
    type_name = "custom"

    def get_open_message(self, user, title: str) -> str:
        message = self.bot.ticket_system.get("ticket_messages", {}).get("custom", "")
        if message:
            return message.format(mention=user.mention, name=user.name, id=user.id, guild=user.guild.name, display_name=user.display_name, title=title)
        return (
            f"📝 **Ticket**\n"
            f"Użytkownik: {user.mention}\n"
            f"Tytuł: **{title}**\n\n"
            "Opisz proszę swój problem lub zapytanie."
        )

    def get_closed_message(self) -> str:
        return "Ticket został zamknięty."

    def get_reopened_message(self) -> str:
        return "Ticket został ponownie otwarty."