class Slots:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id: INTEGER NOT NULL,
    mission_id: INTEGER NOT NULL,
    name: TEXT NOT NULL,
    user_id: INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY(mission_id) REFERENCES missions(id) ON DELETE CASCADE,
    FOREIGN KEY(message_id) REFERENCES squads(message_id) ON DELETE CASCADE
    """
    @staticmethod
    async def create(db, mission_id: int, message_id: int, slots: list[str]):
        """Creates slots for a mission

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
            message_id (int): Message id
            slots (list[str]): List of slot names
        """
        for slot in slots:
            await db.conn.execute(
                "INSERT INTO slots (message_id, mission_id, name) VALUES (?, ?, ?)",
                (message_id, mission_id, slot)
            )
        await db.conn.commit()
        
    @staticmethod
    async def list(db):
        """Lists all slots

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: message_id, id, name, user_id
        """
        cursor = await db.conn.execute(
            "SELECT message_id, id, name, user_id FROM slots",
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get(db, message_id: int):
        """Gets slots by message id

        Args:
            db (_type_): Database to be used
            message_id (int): Message id
        Returns:
            fetchall: id, name, user_id
        """
        cursor = await db.conn.execute(
            "SELECT id, name, user_id FROM slots WHERE message_id = ?",
            (message_id,)
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get_by_mission(db, mission_id: int):
        """Gets slots by mission id

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
        Returns:
            fetchall: message_id, id, name, user_id
        """
        cursor = await db.conn.execute(
            "SELECT message_id, id, name, user_id FROM slots WHERE mission_id = ?",
            (mission_id,)
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get_by_mission_and_user(db, mission_id: int, user_id: int):
        """Gets slot by user id and mission id

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
            user_id (int): User id
        Returns:
            fetchone: id, message_id, mission_id, name, user_id
        """
        cursor = await db.conn.execute(
            "SELECT id, message_id, mission_id, name, user_id FROM slots WHERE mission_id = ? AND user_id = ?",
            (mission_id, user_id)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def delete_by_id_message(db, message_id: int):
        """Deletes slots by message id

        Args:
            db (_type_): Database to be used
            message_id (int): Message id
        """
        await db.conn.execute(
            "DELETE FROM slots WHERE message_id = ?",
            (message_id,)
        )
        await db.conn.commit()
    
    @staticmethod
    async def max_id(db):
        """Gets the maximum slot id

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: maximum id
        """
        cursor = await db.conn.execute(
            "SELECT MAX(id) FROM slots",
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def assign_user_to_slot(db, message_id: int, slot_id: str, user_id: int):
        """Assigns a user to a slot

        Args:
            db (_type_): Database to be used
            message_id (int): Message id
            slot_id (str): Slot id
            user_id (int): User id
        """
        # Remove user from any previously assigned slot (across the whole mission)
        await db.conn.execute(
            "UPDATE slots SET user_id = NULL "
            "WHERE mission_id = (SELECT mission_id FROM squads WHERE message_id = ?) "
            "AND user_id = ?",
            (message_id, user_id)
        )
        # Assign user to selected slot
        await db.conn.execute(
            "UPDATE slots SET user_id = ? WHERE message_id = ? AND id = ?",
            (user_id, message_id, slot_id)
        )
        await db.conn.commit()
    
    @staticmethod
    async def remove_user_from_slot(db, mission_id: int, user_id: int):
        """Removes a user from their assigned slot

        Args:
            db (_type_): Database to be used
            mission_id (int): Mission id
            user_id (int): User id
        """
        await db.conn.execute(
            "UPDATE slots SET user_id = NULL WHERE mission_id = ? AND user_id = ?",
            (mission_id, user_id)
        )
        await db.conn.commit()
