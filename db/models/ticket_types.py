class TicketTypes:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    name: TEXT NOT NULL UNIQUE
    """

    @staticmethod
    async def get_id_by_name(db, name: str) -> int | None:
        """Gets ticket type id by name

        Args:
            db (_type_): Database to be used
            name (str): Ticket type name

        Returns:
            fetchone: id
        """
        cursor = await db.conn.execute(
            "SELECT id FROM ticket_types WHERE name = ?",
            (name,)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else None

    @staticmethod
    async def get_name_by_id(db, type_id: int) -> str | None:
        """Gets ticket type name by id

        Args:
            db (_type_): Database to be used
            type_id (int): Ticket type id

        Returns:
            fetchone: name
        """
        cursor = await db.conn.execute(
            "SELECT name FROM ticket_types WHERE id = ?",
            (type_id,)
        )
        row = await cursor.fetchone()
        return str(row[0]) if row else None
