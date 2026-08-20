class Attendance:
    """
    user_id: INTEGER PRIMARY KEY UNIQUE,
    last_mission_date: DATE,
    all_time_missions: INTEGER DEFAULT 0,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    """
    @staticmethod
    async def update_last_mission_date(db, user_id: int, mission_date: str):
        """Updates the last attended mission

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            mission_date (str): Date of the last attended mission
        """
        await db.conn.execute(
            "INSERT INTO attendance (user_id, last_mission_date, all_time_missions) VALUES (?, ?, 1) "
            "ON CONFLICT(user_id) DO UPDATE SET last_mission_date = excluded.last_mission_date, all_time_missions = all_time_missions + 1",
            (user_id, mission_date)
        )
        await db.conn.commit()
        
    @staticmethod
    async def add_mass_attendance(db, user_ids: list[int], mission_date: str):
        """Adds attendance for multiple users

        Args:
            db (_type_): Database to be used
            user_ids (list[int]): List of Discord user ids
            mission_date (str): Date of the attended mission
        """
        for user_id in user_ids:
            await db.conn.execute(
                "INSERT INTO attendance (user_id, last_mission_date, all_time_missions) "
                "VALUES (?, ?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET last_mission_date = excluded.last_mission_date, "
                "all_time_missions = all_time_missions + 1",
                (user_id, mission_date)
            )
        await db.conn.commit()
    
    @staticmethod
    async def get_by_user(db, user_id: int):
        """Gets attendance record by user id

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id

        Returns:
            fetchone: user_id, last_mission_date, all_time_missions
        """
        cursor = await db.conn.execute(
            "SELECT user_id, last_mission_date, all_time_missions FROM attendance WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()
    
    @staticmethod
    async def get_leaderboard(db, limit: int = 10):
        """Gets the attendance leaderboard

        Args:
            db (_type_): Database to be used
            limit (int): Maximum number of records to return

        Returns:
            fetchall: user_id, last_mission_date, all_time_missions
        """
        cursor = await db.conn.execute(
            "SELECT user_id, last_mission_date, all_time_missions FROM attendance ORDER BY all_time_missions DESC LIMIT ?",
            (limit,)
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def update_all_time_missions(db, user_id: int, missions: int):
        """Updates the all-time missions count for a user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            missions (int): New all-time missions count
        """
        await db.conn.execute(
            "UPDATE attendance SET all_time_missions = ? WHERE user_id = ?",
            (missions, user_id)
        )
        cursor = await db.conn.execute("SELECT changes()")
        updated_rows = await cursor.fetchone()
        if not updated_rows or updated_rows[0] == 0:
            await db.conn.execute(
            "INSERT INTO attendance (user_id, last_mission_date, all_time_missions) VALUES (?, NULL, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET all_time_missions = excluded.all_time_missions",
            (user_id, missions)
            )
        await db.conn.commit()
