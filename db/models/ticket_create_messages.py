class TicketCreateMessages:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id: INTEGER NOT NULL UNIQUE,
    message_id: INTEGER NOT NULL UNIQUE,
    categories TEXT
    """

    @staticmethod
    async def save(db, channel_id: int, message_id: int, categories_payload: str):
        """Creates or updates ticket create message

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            message_id (int): Discord message id
            categories_payload (str): JSON payload with categories
        """
        await db.conn.execute(
            "INSERT INTO ticket_create_messages (channel_id, message_id, categories) VALUES (?, ?, ?) "
            "ON CONFLICT(channel_id) DO UPDATE SET message_id = excluded.message_id, categories = excluded.categories",
            (channel_id, message_id, categories_payload)
        )
        await db.conn.commit()

    @staticmethod
    async def list(db):
        """Lists all ticket create messages

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: channel_id, message_id, categories
        """
        cursor = await db.conn.execute(
            "SELECT channel_id, message_id, categories FROM ticket_create_messages",
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def delete_by_message_id(db, message_id: int):
        """Deletes ticket create message by message id

        Args:
            db (_type_): Database to be used
            message_id (int): Discord message id
        """
        await db.conn.execute(
            "DELETE FROM ticket_create_messages WHERE message_id = ?",
            (message_id,)
        )
        await db.conn.commit()
