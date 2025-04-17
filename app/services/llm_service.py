"""
LLMService — REST‑клиент Google Gemini v1beta.
Отправляет фото рецепта, возвращает текст ICS.
"""
from __future__ import annotations

import json
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Final

import requests

from app.config import settings

_API_ROOT: Final = "https://generativelanguage.googleapis.com"
_MODEL_ID: Final = "gemini-2.5-pro-preview-03-25"

# полный промпт, как в примере
_PROMPT: Final[str] = """
Определите медикаменты, указанные в рецепте, и создайте текст ICS файла, который будет задан пользователю внутри тегов `<ics></ics>` для добавления в календарь расписания приема лекарств. Медикаментов может быть много разных с разными расписаниями, поэтому все приемы должны быть включены в календарь.

# Шаги

1. **Анализ рецепта:** 
   - Извлеките информацию о каждом медикаменте, включая название, дозировку и график приема, из предоставленного рецепта. 
   - Убедитесь, что для каждого медикамента информация полностью извлечена и правильно интерпретирована.

2. **Создание ICS файла:**
   - Сформируйте файл формата ICS, чтобы каждое указанное расписание приема медикаментов могло быть добавлено в календарь.
   - Для каждого медикамента укажите название препарата, его дозировку и время приема. Убедитесь, что каждый приём времени указан в формате, совместимом с календарем.

# Формат вывода

- Текст ICS файла включая переводы строк должен быть обернут в теги `<ics></ics>`.

1. Один файл = один VCALENDAR, внутри любое число VEVENT.   
2. UTF‑8 + CRLF; строки > 75 байт переносите, новую строку начинайте пробелом.  
3. У каждого VEVENT уникальный UID вида {uuid}@домен.  
4. DTSTART — первая доза; DTSTAMP — момент генерации; всегда указывайте TZID либо храните всё в UTC.  
5. Повторяемость — RRULE; несколько приёмов в день — BYHOUR (не все календари поддерживают) или отдельные VEVENT.  
6. Напоминания — VALARM с ACTION:DISPLAY и TRIGGER (чаще ‑PT10M).  
7. Конец курса — UNTIL или COUNT в RRULE; отмена дозы — EXDATE.  
8. Любое изменение события — увеличьте SEQUENCE.  
9. Для отмены всего события пришлите VEVENT с тем же UID и METHOD:CANCEL.  
10. Проверяйте файл через ical validator для кроссплатформенности.  

# ПРИМЕР (2 дозы в день):

<ics>
BEGIN:VCALENDAR
PRODID:-//MedRem//1.0//RU
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:morning-550e8400-e29b-41d4-a716-446655440000@medrem
DTSTAMP:20250417T090000Z
DTSTART;TZID=Europe/Warsaw:20250418T080000
SUMMARY:Ибупрофен 200 мг — утро
RRULE:FREQ=DAILY
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT10M
DESCRIPTION:Через 10 минут принять Ибупрофен 200 мг
END:VALARM
END:VEVENT
BEGIN:VEVENT
UID:evening-550e8400-e29b-41d4-a716-446655440000@medrem
DTSTAMP:20250417T090000Z
DTSTART;TZID=Europe/Warsaw:20250418T200000
SUMMARY:Ибупрофен 200 мг — вечер
RRULE:FREQ=DAILY
BEGIN:VALARM
ACTION:DISPLAY
TRIGGER:-PT10M
DESCRIPTION:Через 10 минут принять Ибупрофен 200 мг
END:VALARM
END:VEVENT
END:VCALENDAR
</ics>
""".strip()


class LLMParseError(RuntimeError):
    """Не удалось извлечь ICS‑данные из ответа LLM."""

    def __init__(self, raw_response: str) -> None:  # noqa: D401
        self.raw_response = raw_response
        super().__init__("ICS‑данные не найдены в ответе LLM")


class LLMService:  # pylint: disable=too-few-public-methods
    """Обёртка вокруг REST‑API Gemini."""

    def __init__(self) -> None:
        self._api_key = settings.gemini_api_key

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def generate_ics(self, image_bytes: bytes, mime_type: str) -> str:
        """Принимает байты изображения рецепта, возвращает текст ICS."""
        file_uri = self._upload_file(image_bytes, mime_type)
        raw_text = self._generate_content(file_uri, mime_type)
        return self._extract_ics(raw_text)

    # ------------------------------------------------------------------ #
    # internal helpers
    # ------------------------------------------------------------------ #
    def _upload_file(self, data: bytes, mime_type: str) -> str:
        """Загружает файл на сервер Gemini и возвращает его URI."""
        size = len(data)
        display_name = f"prescription-{uuid.uuid4().hex}{mimetypes.guess_extension(mime_type) or ''}"

        # 1) start resumable session
        start_headers = {
            "X-Goog-Upload-Protocol": "resumable",
            "X-Goog-Upload-Command": "start",
            "X-Goog-Upload-Header-Content-Length": str(size),
            "X-Goog-Upload-Header-Content-Type": mime_type,
            "Content-Type": "application/json",
        }
        start_resp = requests.post(
            f"{_API_ROOT}/upload/v1beta/files?key={self._api_key}",
            headers=start_headers,
            json={"file": {"display_name": display_name}},
            timeout=30,
        )
        start_resp.raise_for_status()
        upload_url = start_resp.headers["X-Goog-Upload-URL"]

        # 2) upload bytes & finalize
        up_headers = {
            "X-Goog-Upload-Command": "upload, finalize",
            "X-Goog-Upload-Offset": "0",
            "Content-Length": str(size),
        }
        up_resp = requests.post(upload_url, headers=up_headers, data=data, timeout=60)
        up_resp.raise_for_status()
        return up_resp.json()["file"]["uri"]

    def _generate_content(self, file_uri: str, mime_type: str) -> str:
        """Отправляет запрос в модель и возвращает её сырой текстовый ответ."""
        url = f"{_API_ROOT}/v1beta/models/{_MODEL_ID}:generateContent?key={self._api_key}"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "mimeType": mime_type,
                                "fileUri": file_uri,
                            }
                        },
                        {"text": _PROMPT},
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "text/plain",
            },
        }
        resp = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    # ------------------------------------------------------------------ #
    # ICS extraction
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_ics(text: str) -> str:
        """
        Извлекает содержимое ICS.

        Порядок попыток:
        1. Между тегами <ics>...</ics>.
        2. Внутри тройных бэктиков ```ics ... ```.
        3. Блок BEGIN:VCALENDAR ... END:VCALENDAR.
        4. Если ничего не найдено — LLMParseError.
        """
        # 1) <ics>...</ics>
        tag_match = re.search(r"<ics>(.*?)</ics>", text, re.S | re.I)
        if tag_match:
            return tag_match.group(1).strip()

        # 2) ```ics ... ```
        fence_match = re.search(r"```(?:ics)?\s*(BEGIN:VCALENDAR.*?END:VCALENDAR)```", text, re.S | re.I)
        if fence_match:
            return fence_match.group(1).strip()

        # 3) сырой блок VCALENDAR
        cal_match = re.search(r"BEGIN:VCALENDAR.*?END:VCALENDAR", text, re.S | re.I)
        if cal_match:
            return cal_match.group(0).strip()

        # 4) ничего не удалось
        raise LLMParseError(text)
