# app/routers/prescription.py
from pathlib import Path

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, RedirectResponse
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


@router.get("/result/{uid}", response_class=HTMLResponse)
async def result_page(request: Request, uid: str):
    """
    UID — имя файла .ics без расширения.  
    Ставим заголовки no‑store/no‑cache, чтобы страница никогда не кэшировалась.
    """
    ics_path = Path("static/ics") / f"{uid}.ics"
    if not ics_path.exists():
        raise HTTPException(status_code=404, detail="ICS file not found")

    ics_url = request.url_for("static", path=f"ics/{ics_path.name}")
    ics_text = ics_path.read_text(encoding="utf-8")

    qr_b64_ics_text = qr_service.generate_base64_png(ics_text)
    qr_b64_link = qr_service.generate_base64_png(ics_url)

    response = templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "ics_url": ics_url,
            "qr_b64_ics": qr_b64_ics_text,
            "qr_b64_link": qr_b64_link,
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


@router.post("/upload")  # <‑ убрали response_class — будет RedirectResponse
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
    # сохранение ICS и редирект на результат
    # ------------------------------------------------------------------ #
    ics_path: Path = ics_service.save(ics_text)

    # POST‑Redirect‑GET: абсолютная ссылка гарантирует правильный переход
    return RedirectResponse(
        url=request.url_for("result_page", uid=ics_path.stem),
        status_code=status.HTTP_303_SEE_OTHER,
    )
