class Blacklist:
    """
    user_id: INTEGER PRIMARY KEY UNIQUE, 
    reason: TEXT,
    end_at: TIMESTAMP DEFAULT NULL,
    added_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    """
    @staticmethod
    async def add_to_blacklist(db, user_id: int, reason: str, end_at: str | None = None):
        """Adds a user to the blacklist

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            reason (str): Reason for blacklisting
            end_at (str, optional): End date of the blacklist. Defaults to None.
        """
        await db.conn.execute(
            "INSERT INTO blacklist (user_id, reason, end_at) VALUES (?, ?, ?)"
            "ON CONFLICT(user_id) DO UPDATE SET reason = excluded.reason, end_at = excluded.end_at, added_at = CURRENT_TIMESTAMP",
            (user_id, reason, end_at)
        )
        await db.conn.commit()
    
    @staticmethod
    async def remove_from_blacklist(db, user_id: int):
        """Removes a user from the blacklist

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
        """
        await db.conn.execute(
            "DELETE FROM blacklist WHERE user_id = ?",
            (user_id,)
        )
        await db.conn.commit()
        
    @staticmethod
    async def list(db):
        """Lists all blacklisted users

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: user_id, reason, end_at, added_at, username
        """
        cursor = await db.conn.execute(
            "SELECT blacklist.user_id, reason, end_at, added_at, username FROM blacklist JOIN users ON blacklist.user_id = users.user_id",
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get(db, user_id: int):
        """Gets blacklisted user by id

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id

        Returns:
            fetchone: user_id, reason, end_at, added_at
        """
        cursor = await db.conn.execute(
            "SELECT user_id, reason, end_at, added_at FROM blacklist WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def is_blacklisted(db, user_id: int) -> bool:
        """Checks if a user is blacklisted

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id

        Returns:
            bool: True if blacklisted, False otherwise
        """
        cursor = await db.conn.execute(
            "SELECT 1 FROM blacklist WHERE user_id = ? AND (end_at IS NULL OR end_at > CURRENT_TIMESTAMP)",
            (user_id,)
        )
        result = await cursor.fetchone()
        return result is not None
