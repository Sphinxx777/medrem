from pydantic import BaseModel, HttpUrl


class UploadResponse(BaseModel):
    ics_url: HttpUrl
    qr_png_base64: str          # QR с ссылкой
    qr_ics_png_base64: str      # QR с текстом ICS
