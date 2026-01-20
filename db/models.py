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
            fetchall: user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild
        """
        cursor = await db.conn.execute(
            "SELECT user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild FROM users",
        )
        return await cursor.fetchall()
        
    @staticmethod
    async def get_user(db, user_id: int):
        """Gets user by id

        Args:
            db (_type_): Database to be used
            user_id (int): Discord user id

        Returns:
            fetchone: user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild
        """
        cursor = await db.conn.execute(
            "SELECT user_id, username, level, experience, rank_id, joined_at, last_message_at, on_guild "
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
    async def update_users_on_startup(db, users: tuple[int, str]):
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
        
        
        
        
class Blacklist:
    """
    user_id: INTEGER PRIMARY KEY UNIQUE, 
    reason: TEXT,
    end_at: TIMESTAMP DEFAULT NULL,
    added_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE CASCADE
    """
    @staticmethod
    async def add_to_blacklist(db, user_id: int, reason: str, end_at: str = None):
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
    async def create(db, channel_id: int, name: str, creator_user_id: int, date: str):
        """Creates a new mission

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            name (str): Name of the mission
            creator_user_id (int): Discord user id of the creator.
            date (str): Date of the mission
        """
        await db.conn.execute(
            "INSERT INTO missions (channel_id, name, creator_user_id, date) VALUES (?, ?, ?, ?)",
            (channel_id, name, creator_user_id, date)
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




class Tickets:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id: INTEGER NOT NULL UNIQUE,
    user_id: INTEGER,
    created_at: TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status: BOOLEAN DEFAULT 1,
    type_id INTEGER,
    title TEXT,
    FOREIGN KEY(user_id) REFERENCES users(user_id) ON DELETE SET NULL,
    FOREIGN KEY(type_id) REFERENCES ticket_types(id) ON DELETE SET NULL
    """
    
    @staticmethod
    async def create(db, channel_id: int, user_id: int, type_id: int, title: str):
        """Creates a new ticket

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            user_id (int): Discord user id of the ticket creator.
            type_id (int): Ticket type id
            title (str): Title of the ticket
        """
        await db.conn.execute(
            "INSERT INTO tickets (channel_id, user_id, type_id, title) VALUES (?, ?, ?, ?)",
            (channel_id, user_id, type_id, title)
        )
        await db.conn.commit()

    @staticmethod
    async def get_by_channel(db, channel_id: int):
        """Gets ticket by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id

        Returns:
            fetchone: id, channel_id, user_id, created_at, status, type_id, title
        """
        cursor = await db.conn.execute(
            "SELECT id, channel_id, user_id, created_at, status, type_id, title FROM tickets WHERE channel_id = ?",
            (channel_id,)
        )
        return await cursor.fetchone()

    @staticmethod
    async def list_basic(db):
        """Lists all tickets (basic fields)

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: channel_id, status, type_id, user_id, title
        """
        cursor = await db.conn.execute(
            "SELECT channel_id, status, type_id, user_id, title FROM tickets",
        )
        return await cursor.fetchall()

    @staticmethod
    async def update_status(db, channel_id: int, status: int):
        """Updates ticket status by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            status (int): 1 for open, 0 for closed
        """
        await db.conn.execute(
            "UPDATE tickets SET status = ? WHERE channel_id = ?",
            (status, channel_id)
        )
        await db.conn.commit()

    @staticmethod
    async def delete_by_channel(db, channel_id: int):
        """Deletes ticket by channel id

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
        """
        await db.conn.execute(
            "DELETE FROM tickets WHERE channel_id = ?",
            (channel_id,)
        )
        await db.conn.commit()
        



class TicketTypes:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    name: TEXT NOT NULL UNIQUE
    """

    @staticmethod
    async def get_id_by_name(db, name: str) -> int | None:
        """Gets ticket type id by name

        Args:
            db (_type_): Database to be used
            name (str): Ticket type name

        Returns:
            fetchone: id
        """
        cursor = await db.conn.execute(
            "SELECT id FROM ticket_types WHERE name = ?",
            (name,)
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else None

    @staticmethod
    async def get_name_by_id(db, type_id: int) -> str | None:
        """Gets ticket type name by id

        Args:
            db (_type_): Database to be used
            type_id (int): Ticket type id

        Returns:
            fetchone: name
        """
        cursor = await db.conn.execute(
            "SELECT name FROM ticket_types WHERE id = ?",
            (type_id,)
        )
        row = await cursor.fetchone()
        return str(row[0]) if row else None


class TicketCreateMessages:
    """
    id: INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id: INTEGER NOT NULL UNIQUE,
    message_id: INTEGER NOT NULL UNIQUE,
    categories TEXT
    """

    @staticmethod
    async def save(db, channel_id: int, message_id: int, categories_payload: str):
        """Creates or updates ticket create message

        Args:
            db (_type_): Database to be used
            channel_id (int): Discord channel id
            message_id (int): Discord message id
            categories_payload (str): JSON payload with categories
        """
        await db.conn.execute(
            "INSERT INTO ticket_create_messages (channel_id, message_id, categories) VALUES (?, ?, ?) "
            "ON CONFLICT(channel_id) DO UPDATE SET message_id = excluded.message_id, categories = excluded.categories",
            (channel_id, message_id, categories_payload)
        )
        await db.conn.commit()

    @staticmethod
    async def list(db):
        """Lists all ticket create messages

        Args:
            db (_type_): Database to be used

        Returns:
            fetchall: channel_id, message_id, categories
        """
        cursor = await db.conn.execute(
            "SELECT channel_id, message_id, categories FROM ticket_create_messages",
        )
        return await cursor.fetchall()
    
    @staticmethod
    async def delete_by_message_id(db, message_id: int):
        """Deletes ticket create message by message id

        Args:
            db (_type_): Database to be used
            message_id (int): Discord message id
        """
        await db.conn.execute(
            "DELETE FROM ticket_create_messages WHERE message_id = ?",
            (message_id,)
        )
        await db.conn.commit()