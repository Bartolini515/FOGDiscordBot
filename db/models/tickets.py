class Tickets:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id: INTEGER NOT NULL UNIQUE,
    user_id: INTEGER,
    created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status: BOOLEAN DEFAULT 1,
    type_id INTEGER,
    title TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY(type_id) REFERENCES ticket_types(id) ON DELETE SET NULL
    """
    
    @staticmethod
    async def create(db, channel_id: int, user_id: int, type_id: int, title: str):
        """Creates a new ticket

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            user_id (int): Discord user id of the ticket creator.
            type_id (int): Ticket type id
            title (str): Title of the ticket
        """
        await db.conn.execute(
            "INSERT INTO tickets (channel_id, user_id, type_id, title) VALUES (?, ?, ?, ?)",
            (channel_id, user_id, type_id, title)
        )
        await db.conn.commit()

    @staticmethod
    async def get_by_channel(db, channel_id: int):
        """Gets ticket by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id

        Returns:
            fetchone: id, channel_id, user_id, created_at, status, type_id, title
        """
        cursor = await db.conn.execute(
            "SELECT id, channel_id, user_id, created_at, status, type_id, title FROM tickets WHERE channel_id = ?",
            (channel_id,)
        )
        return await cursor.fetchone()

    @staticmethod
    async def list_basic(db):
        """Lists all tickets (basic fields)

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: channel_id, status, type_id, user_id, title
        """
        cursor = await db.conn.execute(
            "SELECT channel_id, status, type_id, user_id, title FROM tickets",
        )
        return await cursor.fetchall()

    @staticmethod
    async def update_status(db, channel_id: int, status: int):
        """Updates ticket status by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            status (int): 1 for open, 0 for closed
        """
        await db.conn.execute(
            "UPDATE tickets SET status = ? WHERE channel_id = ?",
            (status, channel_id)
        )
        await db.conn.commit()

    @staticmethod
    async def delete_by_channel(db, channel_id: int):
        """Deletes ticket by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
        """
        await db.conn.execute(
            "DELETE FROM tickets WHERE channel_id = ?",
            (channel_id,)
        )
        await db.conn.commit()
        
