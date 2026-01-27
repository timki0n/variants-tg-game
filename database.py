import aiosqlite
from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from config import DATABASE_PATH


@dataclass
class Game:
    id: int
    chat_id: str
    question: str
    correct_answer: str
    fact: str
    phase: str  # collecting | voting | finished
    created_at: datetime
    message_id: Optional[int] = None
    poll_message_id: Optional[int] = None
    poll_id: Optional[str] = None


@dataclass
class Participant:
    id: int
    game_chat_id: str
    user_id: int
    answer: Optional[str]


@dataclass
class GameOption:
    id: int
    game_chat_id: str
    option_index: int
    option_text: str
    author_user_id: Optional[int]  # None = правильна відповідь
    is_correct: bool


@dataclass
class PollVote:
    id: int
    game_chat_id: str
    user_id: int
    option_index: int


@dataclass
class UserScore:
    id: int
    chat_id: str
    user_id: int
    score: int


async def init_db() -> None:
    """Ініціалізує базу даних та створює таблиці."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE NOT NULL,
                question TEXT NOT NULL,
                correct_answer TEXT NOT NULL,
                fact TEXT NOT NULL,
                phase TEXT DEFAULT 'collecting',
                message_id INTEGER,
                poll_message_id INTEGER,
                poll_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS participants (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_chat_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                answer TEXT,
                UNIQUE(game_chat_id, user_id),
                FOREIGN KEY (game_chat_id) REFERENCES games(chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS game_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_chat_id TEXT NOT NULL,
                option_index INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                author_user_id INTEGER,
                is_correct BOOLEAN DEFAULT 0,
                UNIQUE(game_chat_id, option_index),
                FOREIGN KEY (game_chat_id) REFERENCES games(chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS poll_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_chat_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                option_index INTEGER NOT NULL,
                UNIQUE(game_chat_id, user_id),
                FOREIGN KEY (game_chat_id) REFERENCES games(chat_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                score INTEGER DEFAULT 0,
                UNIQUE(chat_id, user_id)
            )
        """)
        await db.commit()


async def upsert_game(
    chat_id: str,
    question: str,
    correct_answer: str,
    fact: str,
    message_id: Optional[int] = None
) -> None:
    """Створює нову гру або оновлює існуючу."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Видаляємо старі дані якщо гра вже існувала
        await db.execute("DELETE FROM participants WHERE game_chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM game_options WHERE game_chat_id = ?", (chat_id,))
        await db.execute("DELETE FROM poll_votes WHERE game_chat_id = ?", (chat_id,))
        
        await db.execute("""
            INSERT INTO games (chat_id, question, correct_answer, fact, phase, message_id)
            VALUES (?, ?, ?, ?, 'collecting', ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                question = excluded.question,
                correct_answer = excluded.correct_answer,
                fact = excluded.fact,
                phase = 'collecting',
                message_id = excluded.message_id,
                poll_message_id = NULL,
                poll_id = NULL,
                created_at = CURRENT_TIMESTAMP
        """, (chat_id, question, correct_answer, fact, message_id))
        await db.commit()


async def get_game_by_chat_id(chat_id: str) -> Optional[Game]:
    """Отримує гру за chat_id."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM games WHERE chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Game(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    question=row["question"],
                    correct_answer=row["correct_answer"],
                    fact=row["fact"],
                    phase=row["phase"],
                    created_at=row["created_at"],
                    message_id=row["message_id"],
                    poll_message_id=row["poll_message_id"],
                    poll_id=row["poll_id"]
                )
    return None


async def get_game_by_poll_id(poll_id: str) -> Optional[Game]:
    """Отримує гру за poll_id."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM games WHERE poll_id = ?",
            (poll_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Game(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    question=row["question"],
                    correct_answer=row["correct_answer"],
                    fact=row["fact"],
                    phase=row["phase"],
                    created_at=row["created_at"],
                    message_id=row["message_id"],
                    poll_message_id=row["poll_message_id"],
                    poll_id=row["poll_id"]
                )
    return None


async def update_game_phase(
    chat_id: str,
    phase: str,
    poll_id: Optional[str] = None,
    poll_message_id: Optional[int] = None
) -> None:
    """Оновлює фазу гри та опціонально poll_id і poll_message_id."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        if poll_id is not None and poll_message_id is not None:
            await db.execute(
                "UPDATE games SET phase = ?, poll_id = ?, poll_message_id = ? WHERE chat_id = ?",
                (phase, poll_id, poll_message_id, chat_id)
            )
        else:
            await db.execute(
                "UPDATE games SET phase = ? WHERE chat_id = ?",
                (phase, chat_id)
            )
        await db.commit()


# ============ Participants ============

async def get_participant(game_chat_id: str, user_id: int) -> Optional[Participant]:
    """Отримує учасника гри."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM participants WHERE game_chat_id = ? AND user_id = ?",
            (game_chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return Participant(
                    id=row["id"],
                    game_chat_id=row["game_chat_id"],
                    user_id=row["user_id"],
                    answer=row["answer"]
                )
    return None


async def get_participant_by_user(user_id: int) -> Optional[Participant]:
    """Отримує учасника за user_id (для активної гри у фазі collecting)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT p.* FROM participants p
            JOIN games g ON p.game_chat_id = g.chat_id
            WHERE p.user_id = ? AND g.phase = 'collecting'
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return Participant(
                    id=row["id"],
                    game_chat_id=row["game_chat_id"],
                    user_id=row["user_id"],
                    answer=row["answer"]
                )
    return None


async def get_participants_count(chat_id: str) -> int:
    """Отримує кількість учасників гри."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM participants WHERE game_chat_id = ?",
            (chat_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_participants_with_answers(chat_id: str) -> list[Participant]:
    """Отримує всіх учасників гри з їхніми відповідями."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM participants WHERE game_chat_id = ? AND answer IS NOT NULL",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                Participant(
                    id=row["id"],
                    game_chat_id=row["game_chat_id"],
                    user_id=row["user_id"],
                    answer=row["answer"]
                )
                for row in rows
            ]


async def add_participant(game_chat_id: str, user_id: int) -> bool:
    """Додає учасника до гри. Повертає True якщо успішно."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO participants (game_chat_id, user_id) VALUES (?, ?)",
                (game_chat_id, user_id)
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def update_participant_answer(user_id: int, answer: str) -> bool:
    """Оновлює відповідь учасника. Повертає True якщо успішно."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        cursor = await db.execute("""
            UPDATE participants 
            SET answer = ?
            WHERE user_id = ? AND answer IS NULL
            AND game_chat_id IN (SELECT chat_id FROM games WHERE phase = 'collecting')
        """, (answer, user_id))
        await db.commit()
        return cursor.rowcount > 0


# ============ Game Options ============

async def save_game_options(chat_id: str, options: list[tuple[int, str, Optional[int], bool]]) -> None:
    """Зберігає варіанти відповідей для Poll.
    
    options: list of (option_index, option_text, author_user_id, is_correct)
    """
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM game_options WHERE game_chat_id = ?", (chat_id,))
        await db.executemany("""
            INSERT INTO game_options (game_chat_id, option_index, option_text, author_user_id, is_correct)
            VALUES (?, ?, ?, ?, ?)
        """, [(chat_id, idx, text, author, correct) for idx, text, author, correct in options])
        await db.commit()


async def get_game_options(chat_id: str) -> list[GameOption]:
    """Отримує варіанти відповідей для гри."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM game_options WHERE game_chat_id = ? ORDER BY option_index",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                GameOption(
                    id=row["id"],
                    game_chat_id=row["game_chat_id"],
                    option_index=row["option_index"],
                    option_text=row["option_text"],
                    author_user_id=row["author_user_id"],
                    is_correct=bool(row["is_correct"])
                )
                for row in rows
            ]


# ============ Poll Votes ============

async def save_poll_vote(chat_id: str, user_id: int, option_index: int) -> None:
    """Зберігає голос користувача (тільки перший, зміни ігноруються)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO poll_votes (game_chat_id, user_id, option_index)
            VALUES (?, ?, ?)
        """, (chat_id, user_id, option_index))
        await db.commit()


async def get_poll_votes(chat_id: str) -> list[PollVote]:
    """Отримує всі голоси для гри."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM poll_votes WHERE game_chat_id = ?",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                PollVote(
                    id=row["id"],
                    game_chat_id=row["game_chat_id"],
                    user_id=row["user_id"],
                    option_index=row["option_index"]
                )
                for row in rows
            ]


# ============ User Scores ============

async def add_user_score(chat_id: str, user_id: int, points: int) -> None:
    """Додає бали користувачу."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT INTO user_scores (chat_id, user_id, score)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                score = score + excluded.score
        """, (chat_id, user_id, points))
        await db.commit()


async def get_user_score(chat_id: str, user_id: int) -> int:
    """Отримує бали користувача в чаті."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT score FROM user_scores WHERE chat_id = ? AND user_id = ?",
            (chat_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def get_leaderboard(chat_id: str, limit: int = 10) -> list[UserScore]:
    """Отримує топ гравців в чаті."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM user_scores WHERE chat_id = ? ORDER BY score DESC LIMIT ?",
            (chat_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [
                UserScore(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    user_id=row["user_id"],
                    score=row["score"]
                )
                for row in rows
            ]
