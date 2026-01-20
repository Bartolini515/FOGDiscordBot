import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.models import TicketTypes


class Utilities(commands.Cog):
    """Utility commands for the bot."""
    def __init__(self, bot:commands.Bot):
        self.bot = bot


    # =========== Information section ===========
    # /ping
    @app_commands.command(
        name="ping",
        description="Sprawdź opóźnienie bota",
    )
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)  # Convert to milliseconds
        await interaction.response.send_message(f"Pong 🏓! Opóźnienie: {latency}ms", ephemeral=True)
    
    # /info
    @app_commands.command(
        name="info",
        description="Informacje o bocie",
    )
    async def info(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Informacje o bocie",
            description="Bot zajmuje się ułatwianiem życia.",
            color=discord.Color.light_grey()
        )
        embed.add_field(name="Developer", value="Bartolini", inline=False)
        embed.add_field(name="Wersja", value=self.bot.technical_info.get("version", "Unknown"), inline=False)
        embed.add_field(name="Ostatnia Aktualizacja", value=self.bot.technical_info.get("last_updated", "Unknown"), inline=False)
        embed.add_field(name="Data Uruchomienia", value=self.bot.technical_info.get("current_run_date", "Unknown").split("T")[0], inline=False)
        start_dt = datetime.fromisoformat(self.bot.technical_info.get("current_run_date", datetime.now().isoformat()))
        uptime = datetime.now() - start_dt
        uptime_str = str(uptime).split(".")[0]  # drop microseconds
        embed.add_field(name="Czas działania", value=uptime_str, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        
        
        
    # =========== Permissions section ===========
    # /permissions_list
    @app_commands.command(
        name="permissions_list",
        description="Wyświetl role i użytkowników z uprawnieniami do określonych kategorii",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def permissions_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Lista uprawnień",
            color=discord.Color.blue()
        )

        for kategoria, ids in self.bot.permissions.items():
            if not ids:
                embed.add_field(name=kategoria, value="Brak uprawnień", inline=False)
                continue

            mentions = []
            for id_str in ids:
                id_int = int(id_str)
                user = interaction.guild.get_member(id_int)
                if user:
                    mentions.append(user.mention)
                    continue
                role = interaction.guild.get_role(id_int)
                if role:
                    mentions.append(role.mention)
            if mentions:
                embed.add_field(name=kategoria, value=", ".join(mentions), inline=False)
            else:
                embed.add_field(name=kategoria, value="Brak uprawnień", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    # /permissions_add
    @app_commands.command(
        name="permissions_add",
        description="Dodaj role lub użytkownika do uprawnionych kategorii",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        kategoria="Kategoria do której chcesz dodać uprawnienia",
        uzytkownik="Użytkownik do dodania (opcjonalne)",
        rola="Rola do dodania (opcjonalne)"
    )
    async def permissions_add(self, interaction: discord.Interaction, kategoria: str, uzytkownik: discord.Member = None, rola: discord.Role = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        if kategoria not in self.bot.permissions:
            await interaction.response.send_message(f"Kategoria '{kategoria}' nie istnieje.", ephemeral=True)
            return

        if uzytkownik is None and rola is None:
            await interaction.response.send_message("Musisz podać użytkownika lub rolę do dodania.", ephemeral=True)
            return

        if uzytkownik:
            user_id = str(uzytkownik.id)
            if user_id in self.bot.permissions[kategoria]:
                await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} już posiada uprawnienia w kategorii '{kategoria}'.", ephemeral=True)
                return
            self.bot.permissions[kategoria].append(user_id)

        if rola:
            role_id = str(rola.id)
            if role_id in self.bot.permissions[kategoria]:
                await interaction.response.send_message(f"Rola {rola.mention} już posiada uprawnienia w kategorii '{kategoria}'.", ephemeral=True)
                return
            self.bot.permissions[kategoria].append(role_id)

        await interaction.response.send_message("Uprawnienia zostały zaktualizowane.", ephemeral=True)
        
    # /permissions_remove
    @app_commands.command(
        name="permissions_remove",
        description="Usuń role lub użytkownika z uprawnionych kategorii",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        kategoria="Kategoria z której chcesz usunąć uprawnienia",
        uzytkownik="Użytkownik do usunięcia (opcjonalne)",
        rola="Rola do usunięcia (opcjonalne)"
    )
    async def permissions_remove(self, interaction: discord.Interaction, kategoria: str, uzytkownik: discord.Member = None, rola: discord.Role = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        if kategoria not in self.bot.permissions:
            await interaction.response.send_message(f"Kategoria '{kategoria}' nie istnieje.", ephemeral=True)
            return

        if uzytkownik is None and rola is None:
            await interaction.response.send_message("Musisz podać użytkownika lub rolę do usunięcia.", ephemeral=True)
            return

        if uzytkownik:
            user_id = str(uzytkownik.id)
            if user_id not in self.bot.permissions[kategoria]:
                await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} nie posiada uprawnień w kategorii '{kategoria}'.", ephemeral=True)
                return
            self.bot.permissions[kategoria].remove(user_id)

        if rola:
            role_id = str(rola.id)
            if role_id not in self.bot.permissions[kategoria]:
                await interaction.response.send_message(f"Rola {rola.mention} nie posiada uprawnień w kategorii '{kategoria}'.", ephemeral=True)
                return
            self.bot.permissions[kategoria].remove(role_id)

        await interaction.response.send_message("Uprawnienia zostały zaktualizowane.", ephemeral=True)
        
        
        
        
    # =========== Channels section ===========
    # /channels_list
    @app_commands.command(
        name="channels_list",
        description="Wyświetl kanały przypisane do określonych kategorii",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def channels_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Lista kanałów",
            color=discord.Color.green()
        )

        for kategoria, channel_id in self.bot.channels.items():
            channel = interaction.guild.get_channel(int(channel_id))
            if channel:
                embed.add_field(name=kategoria, value=channel.mention, inline=False)
            else:
                embed.add_field(name=kategoria, value="Brak przypisanego kanału", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    # /channels_set
    @app_commands.command(
        name="channels_set",
        description="Ustaw kanały dla określonych kategorii",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        kategoria="Kategoria do której chcesz przypisać kanał",
        kanal="Kanał do przypisania"
    )
    async def channels_set(self, interaction: discord.Interaction, kategoria: str, kanal: discord.TextChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        if kategoria not in self.bot.channels:
            await interaction.response.send_message(f"Kategoria '{kategoria}' nie istnieje.", ephemeral=True)
            return

        self.bot.channels[kategoria] = kanal.id
        await interaction.response.send_message(f"Kanał dla kategorii '{kategoria}' został ustawiony na {kanal.mention}.", ephemeral=True)
        
    # /channels_remove
    @app_commands.command(
        name="channels_remove",
        description="Usuń kanały przypisane do określonych kategorii",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        kategoria="Kategoria z której chcesz usunąć kanał"
    )
    async def channels_remove(self, interaction: discord.Interaction, kategoria: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        if kategoria not in self.bot.channels:
            await interaction.response.send_message(f"Kategoria '{kategoria}' nie istnieje.", ephemeral=True)
            return

        self.bot.channels[kategoria] = None
        await interaction.response.send_message(f"Kanał dla kategorii '{kategoria}' został usunięty.", ephemeral=True)
    
    
    
    
    # =========== Ticket Types section ===========
    # TODO: Test this
    #/ticket_categories_list
    @app_commands.command(
        name="ticket_categories_list",
        description="Wyświetl dostępne kategorie ticketów",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_types_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        
        categories = self.bot.ticket_system.get("ticket_categories", [])
        if not categories:
            await interaction.response.send_message("Brak dostępnych kategorii ticketów.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Dostępne kategorie ticketów",
            color=discord.Color.purple()
        )

        for category in categories:
            embed.add_field(name=f"{category.get("name", "Brak nazwy")} (<#{category.get("category_id", "0")}>)", value=category.get("description", "Brak opisu"), inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # TODO: Test this
    #/ticket_categories_add
    @app_commands.command(
        name="ticket_categories_add",
        description="Dodaj nową kategorię ticketów",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        name="Nazwa nowej kategorii ticketów",
        description="Opis nowej kategorii ticketów",
        category="Kategoria Discord do przypisania ticketów"
    )
    async def ticket_categories_add(self, interaction: discord.Interaction, name: str, description: str, category: discord.CategoryChannel):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        categories = self.bot.ticket_system.get("ticket_categories", [])
        categories.append({"name": name, "description": description, "type": "custom", "category_id": category.id})
        self.bot.ticket_system["ticket_categories"] = categories

        await interaction.response.send_message(f"Kategoria ticketów '{name}' została dodana.", ephemeral=True)
    
    # TODO: Test this
    #/ticket_categories_remove
    @app_commands.command(
        name="ticket_categories_remove",
        description="Usuń kategorię ticketów",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        name="Nazwa kategorii ticketów do usunięcia"
    )
    async def ticket_categories_remove(self, interaction: discord.Interaction, name: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        categories = self.bot.ticket_system.get("ticket_categories", [])
        categories_copy = categories.copy()
        for category in categories:
            if category.get("name") == name:
                if category.get("type") != "custom":
                    await interaction.response.send_message(f"Kategoria ticketów '{name}' nie może zostać usunięta, ponieważ nie jest kategorią niestandardową.", ephemeral=True)
                    return
                categories.remove(category)
                break

        if len(categories) == len(categories_copy):
            await interaction.response.send_message(f"Kategoria ticketów '{name}' nie została znaleziona.", ephemeral=True)
            return

        self.bot.ticket_system["ticket_categories"] = categories
        await interaction.response.send_message(f"Kategoria ticketów '{name}' została usunięta.", ephemeral=True)
        
        
        
        
    # =========== Trigger Messages section ===========
    # /triggers_list
    # TODO: Implement list, add, delete, edit

async def setup(bot:commands.Bot):
    await bot.add_cog(Utilities(bot))