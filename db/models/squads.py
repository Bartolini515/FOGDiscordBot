class Squads:
    """
    message_id: INTEGER NOT NULL PRIMARY KEY UNIQUE,
    mission_id: INTEGER NOT NULL,
    name: TEXT NOT NULL,
    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE
    """
    @staticmethod
    async def create(db, mission_id: int, message_id: int, name: str):
        """Creates a squad for a mission

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
            message_id (int): Message id
            name (str): Name of the squad
        """
        await db.conn.execute(
            "INSERT INTO squads (mission_id, message_id, name) VALUES (?, ?, ?)",
            (mission_id, message_id, name)
        )
        await db.conn.commit()
    
    @staticmethod
    async def get(db, message_id: int):
        """Gets squad by message id

        Args:
            db (_type_): Database to be used
            message_id (int): Message id

        Returns:
            fetchone: message_id, mission_id, name
        """
        cursor = await db.conn.execute(
            "SELECT message_id, mission_id, name FROM squads WHERE message_id = ?",
            (message_id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def get_by_mission(db, mission_id: int):
        """Gets squads by mission id

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id

        Returns:
            fetchall: message_id, mission_id, name
        """
        cursor = await db.conn.execute(
            "SELECT message_id, mission_id, name FROM squads WHERE mission_id = ?",
            (mission_id,)
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get_by_name(db, mission_id: int, name: str):
        """Gets squad by name and mission id

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
            name (str): Name of the squad

        Returns:
            fetchone: message_id, mission_id, name
        """
        cursor = await db.conn.execute(
            "SELECT message_id, mission_id, name FROM squads WHERE mission_id = ? AND name = ?",
            (mission_id, name)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def delete(db, message_id: int):
        """Deletes a squad

        Args:
            db (_type_): Database to be used
            message_id (int): Message id
        """
        await db.conn.execute(
            "DELETE FROM squads WHERE message_id = ?",
            (message_id,)
        )
        await db.conn.commit()
        
        
        
        
