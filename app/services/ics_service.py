from pathlib import Path
import uuid
from datetime import datetime, timezone

ICS_DIR = Path("static/ics")
ICS_DIR.mkdir(parents=True, exist_ok=True)


class ICSService:
    """Сохраняет текст ICS в файл и возвращает его путь."""  # noqa: D401

    def save(self, ics_text: str) -> Path:
        uid = uuid.uuid4().hex
        path = ICS_DIR / f"{uid}.ics"

        if "DTSTAMP:" not in ics_text:
            dtstamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            ics_text = ics_text.replace(
                "BEGIN:VEVENT", f"BEGIN:VEVENT\nDTSTAMP:{dtstamp}", 1
            )

        path.write_text(ics_text, encoding="utf-8", newline="\r\n")
        return path
