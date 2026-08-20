class Trainings:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    name: TEXT NOT NULL,
    channel_id: INTEGER NOT NULL UNIQUE,
    message_id: INTEGER UNIQUE,
    date: DATE NOT NULL,
    created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    creator_user_id: INTEGER,
    FOREIGN KEY(creator_user_id) REFERENCES users(user_id) ON DELETE SET NULL
    """
    
    @staticmethod
    async def create(db, channel_id: int, name: str, creator_user_id: int, date: str):
        """Creates a new training

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            name (str): Name of the training
            creator_user_id (int): Discord user id of the creator.
            date (str): Date of the training
        """
        cursor = await db.conn.execute(
            "INSERT INTO trainings (channel_id, name, creator_user_id, date) VALUES (?, ?, ?, ?)",
            (channel_id, name, creator_user_id, date)
        )
        await db.conn.commit()
        return cursor.lastrowid
        
    @staticmethod
    async def list(db):
        """Lists all trainings

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: id, name, channel_id, message_id, created_at, creator_user_id, date
        """
        cursor = await db.conn.execute(
            "SELECT id, name, channel_id, message_id, created_at, creator_user_id, date FROM trainings",
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get(db, training_id: int):
        """Gets training by id

        Args:
            db (_type_): Database to be used
            training_id (int): Training id

        Returns:
            fetchone: id, name, channel_id, message_id, created_at, creator_user_id, date
        """
        cursor = await db.conn.execute(
            "SELECT id, name, channel_id, message_id, created_at, creator_user_id, date FROM trainings WHERE id = ?",
            (training_id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def get_channel(db, channel_id: int):
        """Gets training by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
        Returns:
            fetchone: id, name, channel_id, message_id, created_at, creator_user_id, date
        """
        cursor = await db.conn.execute(
            "SELECT id, name, channel_id, message_id, created_at, creator_user_id, date FROM trainings WHERE channel_id = ?",
            (channel_id,)
        )
        return await cursor.fetchone()

    @staticmethod
    async def set_message_id(db, training_id: int, message_id: int):
        """Stores the signup message id for a training."""
        await db.conn.execute(
            "UPDATE trainings SET message_id = ? WHERE id = ?",
            (message_id, training_id)
        )
        await db.conn.commit()
    
    @staticmethod
    async def delete(db, training_id: int):
        """Deletes a training

        Args:
            db (_type_): Database to be used
            training_id (int): Training id
        """
        await db.conn.execute(
            "DELETE FROM trainings WHERE id = ?",
            (training_id,)
        )
        await db.conn.commit()
        
    @staticmethod
    async def update(db, training_id: int, name: str, date: str):
        """Updates a training

        Args:
            db (_type_): Database to be used
            training_id (int): Training id
            name (str): Name of the training
            date (str): Date of the training
        """
        await db.conn.execute(
            "UPDATE trainings SET name = ?, date = ? WHERE id = ?",
            (name, date, training_id)
        )
        await db.conn.commit()
        
        
        
        
