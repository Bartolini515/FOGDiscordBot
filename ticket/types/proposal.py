class ProposalTicketType:
    type_name = "proposal"

    def get_open_message(self, user, title: str) -> str:
        return (
            f"💡 **Ticket propozycji**\n"
            f"Użytkownik: {user.mention}\n"
            f"Tytuł: **{title}**\n\n"
            "Opisz proszę swoją propozycję."
        )

    def get_closed_message(self) -> str:
        return "Ticket propozycji został zamknięty."

    def get_reopened_message(self) -> str:
        return "Ticket propozycji został ponownie otwarty."