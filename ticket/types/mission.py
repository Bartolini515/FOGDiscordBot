class MissionTicketType:
    type_name = "mission"

    def get_open_message(self, user, title: str) -> str:
        return (
            f"📌 **Ticket misji**\n"
            f"Użytkownik: {user.mention}\n"
            f"Tytuł: **{title}**\n\n"
            "Opisz proszę szczegóły misji."
        )

    def get_closed_message(self) -> str:
        return "Ticket misji został zamknięty."

    def get_reopened_message(self) -> str:
        return "Ticket misji został ponownie otwarty."