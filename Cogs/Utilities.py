import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime
from db.models import Attendance


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
    
    
    
    
    # =========== Tools section ===========
    # /clear
    @app_commands.command(
        name="clear",
        description="Usuń określoną liczbę wiadomości z kanału",
    )
    @app_commands.describe(
        liczba="Liczba wiadomości do usunięcia (maksymalnie 100)"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def clear(self, interaction: discord.Interaction, liczba: int):
        if liczba < 1 or liczba > 100:
            await interaction.response.send_message("Liczba musi być pomiędzy 1 a 100.", ephemeral=True)
            return
        
        await interaction.response.defer(ephemeral=True, thinking=True)

        deleted = await interaction.channel.purge(limit=liczba)
        await interaction.followup.send(f"Usunięto {len(deleted)} wiadomości.", ephemeral=True)
        
    #/change_user_missions
    @app_commands.command(
        name="change_user_missions",
        description="Zmień ilość misji użytkownika",
    )
    @app_commands.describe(
        liczba="Nowa ilość misji użytkownika"
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def change_user_missions(self, interaction: discord.Interaction, liczba: int):
        if liczba < 0:
            await interaction.response.send_message("Liczba misji nie może być ujemna.", ephemeral=True)
            return
        
        await Attendance.update_all_time_missions(self.bot.db, interaction.user.id, liczba)
        await interaction.response.send_message(f"Ilość misji użytkownika została zmieniona na {liczba}.", ephemeral=True)
    
    
    
    
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
            user_id = uzytkownik.id
            if user_id in self.bot.permissions[kategoria]:
                await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} już posiada uprawnienia w kategorii '{kategoria}'.", ephemeral=True)
                return
            self.bot.permissions[kategoria].append(user_id)

        if rola:
            role_id = rola.id
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
            user_id = uzytkownik.id
            if user_id not in self.bot.permissions[kategoria]:
                await interaction.response.send_message(f"Użytkownik {uzytkownik.mention} nie posiada uprawnień w kategorii '{kategoria}'.", ephemeral=True)
                return
            self.bot.permissions[kategoria].remove(user_id)

        if rola:
            role_id = rola.id
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
        category="Kategoria Discord do przypisania ticketów",
        prompt_title="Czy wymagać tytułu ticketu"
    )
    async def ticket_categories_add(self, interaction: discord.Interaction, name: str, description: str, category: discord.CategoryChannel, prompt_title: bool = False):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        categories = self.bot.ticket_system.get("ticket_categories", [])
        categories.append({"name": name, "description": description, "type": "custom", "category_id": category.id, "prompt_title": prompt_title})
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
    # TODO: Test this
    @app_commands.command(
        name="triggers_list",
        description="Wyświetl zdefiniowane wiadomości wyzwalające",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def triggers_list(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        triggers = self.bot.message_triggers
        if not triggers:
            await interaction.response.send_message("Brak zdefiniowanych wiadomości wyzwalających.", ephemeral=True)
            return

        embed = discord.Embed(
            title="Zdefiniowane wiadomości wyzwalające",
            color=discord.Color.blue()
        )

        for trigger in triggers:
            keyword = trigger.get("keyword", "Brak")
            response = trigger.get("response", "Brak")
            case_sensitive = trigger.get("case_sensitive", False)
            whole_word = trigger.get("whole_word", False)
            # channels = trigger.get("channels", [])
            # roles = trigger.get("roles", [])
            enabled = trigger.get("enabled", True)
            cooldown_seconds = trigger.get("cooldown_seconds", 0)
            description = trigger.get("description", "Brak opisu")

            # channels_str = ", ".join(f"<#{cid}>" for cid in channels) if channels else "Wszystkie"
            # roles_str = ", ".join(f"<@&{rid}>" for rid in roles) if roles else "Wszystkie"

            embed.add_field(
            name=f"**Trigger**: *{keyword}*",
            value=(
                f"**Response:** {response}\n"
                f"**Case sensitive:** {case_sensitive}\n"
                f"**Whole word:** {whole_word}\n"
                f"**Enabled:** {enabled}\n"
                f"**Cooldown:** {cooldown_seconds}s\n"
                # f"**Channels:** {channels_str}\n"
                # f"**Roles:** {roles_str}\n"
                f"**Description:** {description}"
            ),
            inline=False,
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    # /triggers_add
    # TODO: Test this
    @app_commands.command(
        name="triggers_add",
        description="Dodaj nową wiadomość wyzwalającą",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        keyword="Słowo kluczowe wyzwalające",
        response="Odpowiedź bota na wyzwolenie",
        case_sensitive="Czy rozróżniać wielkość liter",
        whole_word="Czy dopasować całe słowo",
        enabled="Czy wyzwalacz jest włączony",
        cooldown_seconds="Czas odnowienia wyzwalacza (w sekundach)",
        description="Opis wyzwalacza"
    )
    async def triggers_add(self, interaction: discord.Interaction, keyword: str, response: str, case_sensitive: bool = False, whole_word: bool = True, enabled: bool = True, cooldown_seconds: int = 0, description: str = ""):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        new_trigger = {
            "keyword": keyword,
            "response": response,
            "case_sensitive": case_sensitive,
            "whole_word": whole_word,
            "enabled": enabled,
            "cooldown_seconds": cooldown_seconds,
            "description": description
        }

        self.bot.message_triggers.append(new_trigger)
        await interaction.response.send_message(f"Nowa wiadomość wyzwalająca została dodana: {keyword}", ephemeral=True)
        
    # /triggers_edit
    # TODO: Test this
    @app_commands.command(
        name="triggers_edit",
        description="Edytuj istniejącą wiadomość wyzwalającą",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        keyword="Słowo kluczowe wyzwalające do edycji",
        new_response="Nowa odpowiedź bota (opcjonalne)",
        new_case_sensitive="Nowa wartość rozróżniania wielkości liter (opcjonalne)",
        new_whole_word="Nowa wartość dopasowania całego słowa (opcjonalne)",
        new_enabled="Nowa wartość włączenia wyzwalacza (opcjonalne)",
        new_cooldown_seconds="Nowa wartość czasu odnowienia wyzwalacza (w sekundach) (opcjonalne)",
        new_description="Nowy opis wyzwalacza (opcjonalne)"
    )
    async def triggers_edit(self, interaction: discord.Interaction, keyword: str, new_response: str = None, new_case_sensitive: bool = None, new_whole_word: bool = None, new_enabled: bool = None, new_cooldown_seconds: int = None, new_description: str = None):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return

        for trigger in self.bot.message_triggers:
            if trigger.get("keyword") == keyword:
                if new_response is not None:
                    trigger["response"] = new_response
                if new_case_sensitive is not None:
                    trigger["case_sensitive"] = new_case_sensitive
                if new_whole_word is not None:
                    trigger["whole_word"] = new_whole_word
                if new_enabled is not None:
                    trigger["enabled"] = new_enabled
                if new_cooldown_seconds is not None:
                    trigger["cooldown_seconds"] = new_cooldown_seconds
                if new_description is not None:
                    trigger["description"] = new_description

                await interaction.response.send_message(f"Wiadomość wyzwalająca '{keyword}' została zaktualizowana.", ephemeral=True)
                return

        await interaction.response.send_message(f"Wiadomość wyzwalająca '{keyword}' nie została znaleziona.", ephemeral=True)
        
    # /triggers_remove
    # TODO: Test this
    @app_commands.command(
        name="triggers_remove",
        description="Usuń istniejącą wiadomość wyzwalającą",
        extras={"category": "Administracja"},
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(
        keyword="Słowo kluczowe wyzwalające do usunięcia"
    )
    async def triggers_remove(self, interaction: discord.Interaction, keyword: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Nie masz uprawnień administratora do użycia tej komendy.", ephemeral=True)
            return
        
        for trigger in self.bot.message_triggers:
            if trigger.get("keyword") == keyword:
                self.bot.message_triggers.remove(trigger)
                await interaction.response.send_message(f"Wiadomość wyzwalająca '{keyword}' została usunięta.", ephemeral=True)
                return

        await interaction.response.send_message(f"Wiadomość wyzwalająca '{keyword}' nie została znaleziona.", ephemeral=True)

async def setup(bot:commands.Bot):
    await bot.add_cog(Utilities(bot))