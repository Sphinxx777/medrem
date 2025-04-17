import base64
from io import BytesIO

import qrcode


class QRService:
    """Генерирует QR‑код, возвращает Base64 PNG."""  # noqa: D401

    def generate_base64_png(self, url: str) -> str:
        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image()
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
