class Missions:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    name: TEXT NOT NULL,
    channel_id: INTEGER NOT NULL UNIQUE,
    date: DATE NOT NULL,
    created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    creator_user_id: INTEGER,
    ping_role_id: INTEGER,
    FOREIGN KEY(creator_user_id) REFERENCES users(user_id) ON DELETE SET NULL
    """
    @staticmethod
    async def create(
        db,
        channel_id: int,
        name: str,
        creator_user_id: int,
        date: str,
        ping_role_id: int | None = None,
    ):
        """Creates a new mission

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            name (str): Name of the mission
            creator_user_id (int): Discord user id of the creator.
            date (str): Date of the mission
            ping_role_id (int, optional): Discord role id to ping for the mission. Defaults to None.
        """
        await db.conn.execute(
            "INSERT INTO missions (channel_id, name, creator_user_id, date, ping_role_id) VALUES (?, ?, ?, ?, ?)",
            (channel_id, name, creator_user_id, date, ping_role_id)
        )
        await db.conn.commit()
        
    @staticmethod
    async def list(db):
        """Lists all missions

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: id, name, channel_id, created_at, creator_user_id, date, ping_role_id
        """
        cursor = await db.conn.execute(
            "SELECT id, name, channel_id, created_at, creator_user_id, date, ping_role_id FROM missions",
        )
        return await cursor.fetchall()
        
    @staticmethod
    async def get(db, mission_id: int):
        """Gets mission by id

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id

        Returns:
            fetchone: id, name, channel_id, created_at, creator_user_id, date, ping_role_id
        """
        cursor = await db.conn.execute(
            "SELECT id, name, channel_id, created_at, creator_user_id, date, ping_role_id FROM missions WHERE id = ?",
            (mission_id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def get_channel(db, channel_id: int):
        """Gets mission by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
        Returns:
            fetchone: id, name, channel_id, created_at, creator_user_id, date, ping_role_id
        """
        cursor = await db.conn.execute(
            "SELECT id, name, channel_id, created_at, creator_user_id, date, ping_role_id FROM missions WHERE channel_id = ?",
            (channel_id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def delete(db, mission_id: int):
        """Deletes a mission

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
        """
        await db.conn.execute(
            "DELETE FROM missions WHERE id = ?",
            (mission_id,)
        )
        await db.conn.commit()
        
    @staticmethod
    async def update(db, mission_id: int, name: str, date: str):
        """Updates a mission

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
            name (str): Name of the mission
            date (str): Date of the mission
        """
        await db.conn.execute(
            "UPDATE missions SET name = ?, date = ? WHERE id = ?",
            (name, date, mission_id)
        )
        await db.conn.commit()
    
    
    
    
