from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ChatType

from database import get_participant_by_user, update_participant_answer


router = Router()

MAX_ANSWER_LENGTH = 100


def truncate_answer(text: str) -> str:
    """Обрізає відповідь до максимальної довжини."""
    if len(text) > MAX_ANSWER_LENGTH:
        return text[:MAX_ANSWER_LENGTH - 3] + "..."
    return text


@router.message(F.chat.type == ChatType.PRIVATE, F.text)
async def handle_variant(message: Message) -> None:
    """Обробник текстових повідомлень - запис варіанту відповіді."""
    user_id = message.from_user.id
    text = message.text
    
    # Ігноруємо команди
    if text.startswith("/"):
        return
    
    # Перевіряємо чи користувач в активній грі
    participant = await get_participant_by_user(user_id)
    
    if not participant:
        await message.answer(
            "Ти не у грі, спочатку додай бота до жвавої групи і почни там гру командою /game"
        )
        return
    
    # Перевіряємо чи вже відповідав
    if participant.answer:
        await message.answer(
            "Ти вже написав(ла) свій варіант, очікуй початку опитування у групі"
        )
        return
    
    # Обрізаємо та зберігаємо відповідь
    answer = truncate_answer(text)
    updated = await update_participant_answer(user_id, answer)
    
    if updated:
        await message.answer(
            "✅ Твою відповідь записано, очікуй початку опитування у групі"
        )
    else:
        await message.answer(
            "Ти вже написав(ла) свій варіант, очікуй початку опитування у групі"
        )
