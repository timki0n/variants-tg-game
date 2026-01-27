import re
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart, CommandObject
from aiogram.enums import ChatType

from database import (
    get_game_by_chat_id,
    get_participant,
    add_participant,
    get_participants_count
)

router = Router()

MAX_PARTICIPANTS = 9  # 10 варіантів в poll - 1 правильна відповідь


@router.message(CommandStart(deep_link=True), F.chat.type == ChatType.PRIVATE)
async def cmd_start_with_game(message: Message, command: CommandObject) -> None:
    """Обробник команди /start {chat_id} - приєднання до гри."""
    user_id = message.from_user.id
    args = command.args
    
    # Перевіряємо що args - це chat_id (число, можливо від'ємне)
    if not args or not re.match(r"^-?\d+$", args):
        await message.answer(
            "Привіт! Я бот для гри Варіанти.\n\n"
            "Щоб почати гру, додай мене до групи і напиши там /game"
        )
        return
    
    game_chat_id = args
    
    # Перевіряємо чи гра існує та активна (фаза збору відповідей)
    game = await get_game_by_chat_id(game_chat_id)
    
    if not game or game.phase != "collecting":
        await message.answer("Активну гру не знайдено або час на відповіді вийшов :(")
        return
    
    # Перевіряємо чи користувач вже брав участь
    participant = await get_participant(game_chat_id, user_id)
    
    if participant:
        if participant.answer:
            await message.answer("Здається ти вже дав свій варіант...")
        else:
            # Вже зареєстрований, але ще не відповів - нагадуємо питання
            await message.answer(
                f"Дай свій правдоподібний але неправильний варіант відповіді на запитання:\n\n"
                f"_{game.question}_",
                parse_mode="Markdown"
            )
        return
    
    # Перевіряємо ліміт учасників
    participants_count = await get_participants_count(game_chat_id)
    if participants_count >= MAX_PARTICIPANTS:
        await message.answer("Вибачте, всі місця зайняті (максимум 9 учасників)")
        return
    
    # Додаємо учасника
    added = await add_participant(game_chat_id, user_id)
    
    if not added:
        await message.answer("Здається ти вже дав свій варіант...")
        return
    
    # Відправляємо питання
    await message.answer(
        f"Дай свій правдоподібний але неправильний варіант відповіді на запитання:\n\n"
        f"_{game.question}_",
        parse_mode="Markdown"
    )


@router.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def cmd_start(message: Message) -> None:
    """Обробник простої команди /start без параметрів."""
    await message.answer(
        "Привіт! Я бот для гри Варіанти.\n\n"
        "Щоб почати гру, додай мене до групи і напиши там /game"
    )
