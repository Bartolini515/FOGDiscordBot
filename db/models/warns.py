class Warns:
    """
    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    reason TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expired BOOLEAN DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
    """
    
    @staticmethod
    async def create(db, user_id: int, reason: str):
        """Creates a warning for a user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            reason (str): Reason for the warning
        """
        await db.conn.execute(
            "INSERT INTO warns (user_id, reason) VALUES (?, ?)",
            (user_id, reason)
        )
        await db.conn.commit()
    
    @staticmethod
    async def list(db):
        """Lists all warnings

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: id, user_id, reason, added_at, expired
        """
        cursor = await db.conn.execute(
            "SELECT id, user_id, reason, added_at, expired FROM warns",
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def list_active(db):
        """Lists all active (non-expired) warnings

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: id, user_id, reason, added_at, expired
        """
        cursor = await db.conn.execute(
            "SELECT id, user_id, reason, added_at, expired FROM warns WHERE expired = 0",
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get(db, id: int):
        """Gets warnings by id

        Args:
            db (_type_): Database to be used
            id (int): Warning id

        Returns:
            fetchone: id, user_id, reason, added_at, expired
        """
        cursor = await db.conn.execute(
            "SELECT id, user_id, reason, added_at, expired FROM warns WHERE id = ?",
            (id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def get_by_user_id(db, user_id: int):
        """Gets warnings by user id

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id

        Returns:
            fetchall: id, user_id, reason, added_at, expired
        """
        cursor = await db.conn.execute(
            "SELECT id, user_id, reason, added_at, expired FROM warns WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get_active_by_user_id(db, user_id: int):
        """Gets active (non-expired) warnings by user id

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id

        Returns:
            fetchall: id, user_id, reason, added_at, expired
        """
        cursor = await db.conn.execute(
            "SELECT id, user_id, reason, added_at, expired FROM warns WHERE user_id = ? AND expired = 0",
            (user_id,)
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def delete(db, id: int):
        """Deletes warning by id

        Args:
            db (_type_): Database to be used
            id (int): Warning id
        """
        await db.conn.execute(
            "DELETE FROM warns WHERE id = ?",
            (id,)
        )
        await db.conn.commit()
        
    @staticmethod
    async def recalculate_expired(db):
        """Recalculates expired status for all warnings based on the current date and expiration rules. Then updates the users warns count accordingly.
        
        Args:
            db (_type_): Database to be used
        """
        await db.conn.execute(
            "UPDATE warns SET expired = 1 WHERE added_at <= datetime ('now', '-30 days')"
        )
        await db.conn.execute(
            "UPDATE users SET warn_count = (SELECT COUNT(*) FROM warns WHERE user_id = users.user_id AND expired = 0)"
        )
        await db.conn.commit()
