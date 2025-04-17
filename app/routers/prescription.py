from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.ics_service import ICSService
from app.services.llm_service import LLMService, LLMParseError
from app.services.qr_service import QRService

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

llm_service = LLMService()
ics_service = ICSService()
qr_service = QRService()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.post("/upload", response_class=HTMLResponse)
async def upload(
    request: Request,
    prescription: UploadFile = File(
        ...,
        description="JPEG или PNG изображение рецепта",
    ),
):
    if prescription.content_type not in ("image/jpeg", "image/png"):
        raise HTTPException(status_code=400, detail="Неверный тип файла")

    image_bytes: bytes = await prescription.read()

    # ------------------------------------------------------------------ #
    # вызов LLM
    # ------------------------------------------------------------------ #
    try:
        ics_text: str = llm_service.generate_ics(image_bytes, prescription.content_type)
    except LLMParseError as exc:
        # Показываем полный ответ LLM пользователю для отладки
        return templates.TemplateResponse(
            "llm_error.html",
            {
                "request": request,
                "message": "Не удалось найти ICS‑данные в ответе LLM. "
                "Ниже приведён полный ответ модели:",
                "raw_text": exc.raw_response,
            },
            status_code=200,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"LLM error: {exc}") from exc

    # ------------------------------------------------------------------ #
    # сохранение ICS и генерация QR
    # ------------------------------------------------------------------ #
    ics_path: Path = ics_service.save(ics_text)
    ics_url = f"{settings.app_base_url.rstrip('/')}/static/ics/{ics_path.name}"
    qr_png_b64: str = qr_service.generate_base64_png(ics_url)

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "ics_url": ics_url,
            "qr_b64": qr_png_b64,
        },
    )
