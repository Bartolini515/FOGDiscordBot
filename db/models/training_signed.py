class TrainingSigned:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    training_id: INTEGER NOT NULL,
    user_id: INTEGER,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY(training_id) REFERENCES trainings(id) ON DELETE CASCADE,
    """
    
    @staticmethod
    async def sign_up(db, training_id: int, user_id: int):
        """Signs up a user for a training

        Args:
            db (_type_): Database to be used
            training_id (int): Training id
            user_id (int): User id
        """        
        await db.conn.execute(
            "INSERT OR IGNORE INTO training_signed (training_id, user_id) VALUES (?, ?)",
            (training_id, user_id)
        )
        await db.conn.commit()

    @staticmethod
    async def is_signed(db, training_id: int, user_id: int) -> bool:
        """Checks if a user is already signed for a training."""
        cursor = await db.conn.execute(
            "SELECT 1 FROM training_signed WHERE training_id = ? AND user_id = ?",
            (training_id, user_id)
        )
        result = await cursor.fetchone()
        return result is not None
    
    @staticmethod
    async def sign_out(db, training_id: int, user_id: int):
        """Cancels a user's signup for a training

        Args:
            db (_type_): Database to be used
            training_id (int): Training id
            user_id (int): User id
        """
        await db.conn.execute(
            "DELETE FROM training_signed WHERE training_id = ? AND user_id = ?",
            (training_id, user_id)
        )
        await db.conn.commit()
        
    @staticmethod
    async def list_by_training(db, training_id: int):
        """Lists all users signed up for a training

        Args:
            db (_type_): Database to be used
            training_id (int): Training id
        Returns:
            fetchall: id, training_id, user_id
        """
        cursor = await db.conn.execute(
            "SELECT id, training_id, user_id FROM training_signed WHERE training_id = ?",
            (training_id,)
        )
        return await cursor.fetchall()
