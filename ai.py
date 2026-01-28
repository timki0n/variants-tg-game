import json
from dataclasses import dataclass
from openai import AsyncOpenAI

from config import OPENAI_API_KEY


client = AsyncOpenAI(api_key=OPENAI_API_KEY)


@dataclass
class GeneratedQuestion:
    question: str
    answer: str
    fact: str


SYSTEM_PROMPT = """Ти генеруєш навчальні питання українською мовою.

Створи ОДНЕ питання на основі наданого факту та правильну відповідь до нього. Запиши також факт українською.

Вимоги до відповіді (answer):
- тільки словесна коротка відповідь
- Максимум 5 слів
- НЕ використовуй: «так» / «ні» / «є» / «немає», числа, дати
- відповідь має бути написана людяно, як в чаті, без дифісів, часто з малої або великої літери
- відповідь має бути конкретною (місто, ім'я, назва, дія, об'єкт тощо)

Формат відповіді — СТРОГО JSON з полями: question, answer, fact"""


async def generate_question(fact_text: str) -> GeneratedQuestion:
    """Генерує питання на основі факту через OpenAI."""
    response = await client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"--ФАКТ--\n{fact_text}"}
        ],
        response_format={"type": "json_object"},
        temperature=0.7
    )
    
    content = response.choices[0].message.content
    data = json.loads(content)
    
    return GeneratedQuestion(
        question=data["question"],
        answer=data["answer"],
        fact=data["fact"]
    )
