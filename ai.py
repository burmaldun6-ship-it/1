import base64
from pathlib import Path

from openai import AsyncOpenAI


PROMPT_PATH = Path(__file__).with_name("prompt.md")


def load_system_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


class AIService:
    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.model = model
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def analyze(
        self,
        image_bytes: bytes,
        nickname: str,
        link: str,
        target_nickname: str,
    ) -> str:
        encoded = base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            "Проанализируй приложенный скриншот строго по системным правилам. "
            f"Ваш ник: {nickname}. "
            f"На какого игрока писать жалобу(ник): {target_nickname}. "
            f"Ссылка на доказательство, которую нужно вставить в итоговую жалобу: {link}"
        )
        response = await self.client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": load_system_prompt().format(nickname=nickname),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{encoded}",
                                "detail": "high",
                            },
                        },
                    ],
                },
            ],
        )
        text = response.choices[0].message.content
        if not text:
            raise RuntimeError("ИИ вернула пустой ответ.")
        return text.strip()
