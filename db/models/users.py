from collections.abc import Sequence

class Users:
    """
    user_id: INTEGER PRIMARY KEY UNIQUE,
    username: TEXT NOT NULL,
    level: INTEGER DEFAULT 1 CHECK(level BETWEEN 1 AND 100),
    experience: INTEGER DEFAULT 0,
    rank_id: INTEGER DEFAULT 1,
    joined_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at: TIMESTAMP DEFAULT NULL,
    on_guild: BOOLEAN DEFAULT 1,
    warn_count: INTEGER DEFAULT 0,
    FOREIGN KEY(rank_id) REFERENCES ranks(id) ON DELETE SET DEFAULT
    """
    @staticmethod
    async def add_user(db, user_id: int, username: str):
        """Adds a new user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            username (str): Discord username
        """
        await db.conn.execute(
            "INSERT INTO users (user_id, username) VALUES (?, ?)"
            "ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, on_guild = 1",
            (user_id, username)
        )
        await db.conn.commit()
        
    @staticmethod
    async def list(db):
        """Lists all users

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild, warn_count
        """
        cursor = await db.conn.execute(
            "SELECT user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild, warn_count FROM users",
        )
        return await cursor.fetchall()
        
    @staticmethod
    async def get_user(db, user_id: int):
        """Gets user by id

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id

        Returns:
            fetchone: user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild, warn_count
        """
        cursor = await db.conn.execute(
            "SELECT user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild, warn_count "
            "FROM users WHERE user_id = ?",
            (user_id,)
        )
        return await cursor.fetchone()
        
    @staticmethod
    async def update_username(db, user_id: int, username: str):
        """Updates the username of a user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            username (str): New Discord username
        """
        await db.conn.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (username, user_id)
        )
        await db.conn.commit()
        
    @staticmethod
    async def update_experience(db, user_id: int, experience: int):
        """Updates the experience of a user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            experience (int): New experience value
        """
        await db.conn.execute(
            "UPDATE users SET experience = ? WHERE user_id = ?",
            (experience, user_id)
        )
        await db.conn.commit()
        
    @staticmethod
    async def update_level(db, user_id: int, level: int):
        """Updates the level of a user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            level (int): New level value
        """
        await db.conn.execute(
            "UPDATE users SET level = ? WHERE user_id = ?",
            (level, user_id)
        )
        await db.conn.commit()
        
    @staticmethod
    async def update_last_message_at(db, user_id: int, timestamp: str):
        """Updates the last message timestamp of a user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            timestamp (str): New timestamp value
        """
        await db.conn.execute(
            "UPDATE users SET last_message_at = ? WHERE user_id = ?",
            (timestamp, user_id)
        )
        await db.conn.commit()
        
    @staticmethod
    async def update_rank(db, user_id: int, rank_id: int):
        """Updates the rank of a user

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
            rank_id (int): New rank id
        """
        await db.conn.execute(
            "UPDATE users SET rank_id = ? WHERE user_id = ?",
            (rank_id, user_id)
        )
        await db.conn.commit()
        
    @staticmethod
    async def update_users_on_startup(db, users: Sequence[tuple[int, str]]):
        """Updates the users table on bot startup to current guild state

        Args:
            db (_type_): Database to be used
            users (tuple[int, str]): Tuple of active Discord user ids and names
        """
        # Set all users to off-guild and then updates those who are present
        await db.conn.execute(
            "UPDATE users SET on_guild = 0"
        )
        for user_id, username in users:
            await db.conn.execute(
                "INSERT INTO users (user_id, username, on_guild) VALUES (?, ?, 1) "
                "ON CONFLICT(user_id) DO UPDATE SET username = excluded.username, on_guild = 1",
                (user_id, username)
            )
        await db.conn.commit()
        
    @staticmethod
    async def change_user_on_guild_status(db, user_id: int):
        """Changes the user on_guild status

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id
        """
        await db.conn.execute(
            "UPDATE users SET on_guild = NOT on_guild WHERE user_id = ?",
            (user_id,)
        )
        await db.conn.commit()
        
    @staticmethod
    async def get_leaderboard(db, limit: int = 10):
        """Gets the leaderboard of users by experience

        Args:
            db (_type_): Database to be used
            limit (int, optional): Number of users to return. Defaults to 10.

        Returns:
            fetchall: user_id, username, level, experience
        """
        cursor = await db.conn.execute(
            "SELECT user_id, username, level, experience FROM users "
            "ORDER BY experience DESC LIMIT ?",
            (limit,)
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def get_warned_users(db):
        """Gets a list of users with active warns

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: user_id, username, warn_count
        """
        cursor = await db.conn.execute(
            "SELECT user_id, username, warn_count FROM users GROUP BY user_id HAVING warn_count > 0"
        )
        return await cursor.fetchall()
        
        
        
        
