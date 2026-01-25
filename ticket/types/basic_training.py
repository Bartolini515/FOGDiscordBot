class BasicTrainingTicketType:
    type_name = "basic_training"

    def get_open_message(self, user, title: str) -> str:
        return (
            f"🗿 **Ticket SzWI**\n"
            f"Użytkownik: {user.mention}\n\n"
            "Skorzystaj z poniższego wzoru, aby zgłosić się na szkolenie SzWI:\n"
            "**Nick:**\n"
            "**Preferowany Termin:**\n"
            "**Ilość godzin w Armie:**\n"
            "**Doświadczenie z innych grup (Opcjonalne):**"
        )

    def get_closed_message(self) -> str:
        return "Ticket szkolenia SzWI został zamknięty."
    def get_reopened_message(self) -> str:
        return "Ticket szkolenia SzWI został ponownie otwarty."
    
    def get_ticket_managers_ids(self, bot):
        return bot.permissions.get("basic_training_tickets_managers", [])
    
    async def on_ticket_created(self, bot, interaction, channel, category, title):
        return
    