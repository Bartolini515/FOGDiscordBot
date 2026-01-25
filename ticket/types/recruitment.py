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
    
    def get_ticket_managers_ids(self, bot):
        return bot.permissions.get("recruiters", [])
    
    async def on_ticket_created(self, bot, interaction, channel, category, title):
        return
