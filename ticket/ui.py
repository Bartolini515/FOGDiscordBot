import logging
import discord


logger = logging.getLogger("fogbot")


class TicketTitleModal(discord.ui.Modal):
    def __init__(self, category_name: str):
        super().__init__(title="Nowy ticket")
        self.category_name = category_name
        self.title_input = discord.ui.TextInput(
            label="Tytuł ticketu",
            placeholder="Wpisz tytuł ticketu",
            max_length=80,
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("Moduł ticketów nie jest dostępny.", ephemeral=True)
            return
        await cog._handle_ticket_title_submit(
            interaction=interaction,
            category_name=self.category_name,
            title=self.title_input.value,
        )


class TicketCreateButton(discord.ui.Button):
    def __init__(self, category_name: str, custom_id: str):
        super().__init__(
            label=f"Utwórz ticket: {category_name}",
            style=discord.ButtonStyle.primary,
            custom_id=custom_id,
        )
        self.category_name = category_name

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("Moduł ticketów nie jest dostępny.", ephemeral=True)
            return
        await cog._start_ticket_creation(interaction=interaction, category_name=self.category_name)


class TicketCreateSelect(discord.ui.Select):
    def __init__(self, categories: list[str], custom_id: str):
        options = [discord.SelectOption(label=cat, value=cat) for cat in categories]
        super().__init__(
            placeholder="Wybierz kategorię ticketu",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=custom_id,
        )
        self.categories = categories

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("Moduł ticketów nie jest dostępny.", ephemeral=True)
            return
        await cog._start_ticket_creation(interaction=interaction, category_name=selected)


class TicketCreateButtonView(discord.ui.View):
    def __init__(self, category_name: str, custom_id: str):
        super().__init__(timeout=None)
        self.add_item(TicketCreateButton(category_name=category_name, custom_id=custom_id))


class TicketCreateSelectView(discord.ui.View):
    def __init__(self, categories: list[str], custom_id: str):
        super().__init__(timeout=None)
        self.add_item(TicketCreateSelect(categories=categories, custom_id=custom_id))


class TicketCloseButton(discord.ui.Button):
    def __init__(self, channel_id: int):
        super().__init__(
            label="Zamknij ticket",
            style=discord.ButtonStyle.danger,
            custom_id=f"ticket_close_{channel_id}",
        )
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("Moduł ticketów nie jest dostępny.", ephemeral=True)
            return
        await cog._handle_ticket_close(interaction=interaction, channel_id=self.channel_id)


class TicketReopenButton(discord.ui.Button):
    def __init__(self, channel_id: int):
        super().__init__(
            label="Otwórz ponownie",
            style=discord.ButtonStyle.success,
            custom_id=f"ticket_reopen_{channel_id}",
        )
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("Moduł ticketów nie jest dostępny.", ephemeral=True)
            return
        await cog._handle_ticket_reopen(interaction=interaction, channel_id=self.channel_id)


class TicketTranscriptButton(discord.ui.Button):
    def __init__(self, channel_id: int):
        super().__init__(
            label="Transkrypt",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ticket_transcript_{channel_id}",
        )
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("Moduł ticketów nie jest dostępny.", ephemeral=True)
            return
        await cog._handle_ticket_transcript(interaction=interaction, channel_id=self.channel_id)


class TicketDeleteButton(discord.ui.Button):
    def __init__(self, channel_id: int):
        super().__init__(
            label="Usuń ticket",
            style=discord.ButtonStyle.danger,
            custom_id=f"ticket_delete_{channel_id}",
        )
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("TicketsCog")
        if cog is None:
            await interaction.response.send_message("Moduł ticketów nie jest dostępny.", ephemeral=True)
            return
        await cog._handle_ticket_delete(interaction=interaction, channel_id=self.channel_id)


class TicketOpenView(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(TicketCloseButton(channel_id=channel_id))


class TicketClosedView(discord.ui.View):
    def __init__(self, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(TicketReopenButton(channel_id=channel_id))
        self.add_item(TicketTranscriptButton(channel_id=channel_id))
        self.add_item(TicketDeleteButton(channel_id=channel_id))