class Ranks:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    name: TEXT NOT NULL,
    role_id INTEGER,
    required_missions: INTEGER NOT NULL
    """
    @staticmethod
    async def get(db, id: int):
        """Gets rank by id

        Args:
            db (_type_): Database to be used
            id (int): Rank id

        Returns:
            fetchone: id, name, role_id, required_missions
        """
        cursor = await db.conn.execute(
            "SELECT id, name, role_id, required_missions FROM ranks WHERE id = ?",
            (id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def get_by_role_id(db, role_id: int):
        """Gets rank by rank id

        Args:
            db (_type_): Database to be used
            role_id (int): Rank id

        Returns:
            fetchone: id, name, role_id, required_missions
        """
        cursor = await db.conn.execute(
            "SELECT id, name, role_id, required_missions FROM ranks WHERE role_id = ?",
            (role_id,)
        )
        return await cursor.fetchone()

    @staticmethod
    async def get_next_rank(db, current_required_missions: int):
        """Gets the next rank based on the current required missions

        Args:
            db (_type_): Database to be used
            current_required_missions (int): Current required missions

        Returns:
            fetchone: id, name, role_id, required_missions
        """
        cursor = await db.conn.execute(
            "SELECT id, name, role_id, required_missions FROM ranks WHERE required_missions > ? ORDER BY required_missions ASC LIMIT 1",
            (current_required_missions,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def get_max_rank(db):
        """Gets the rank with the highest required missions

        Args:
            db (_type_): Database to be used

        Returns:
            fetchone: id, name, role_id, required_missions
        """
        cursor = await db.conn.execute(
            "SELECT id, name, role_id, required_missions FROM ranks ORDER BY required_missions DESC LIMIT 1",
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def list(db):
        """Lists all ranks

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: id, name, role_id, required_missions
        """
        cursor = await db.conn.execute(
            "SELECT id, name, role_id, required_missions FROM ranks ORDER BY required_missions DESC",
        )
        return await cursor.fetchall()
