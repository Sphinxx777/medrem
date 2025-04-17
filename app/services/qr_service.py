import base64
import zlib
from io import BytesIO

import qrcode
from qrcode.exceptions import DataOverflowError


class QRService:
    """Генерирует QR‑код, возвращает Base64 PNG."""  # noqa: D401

    def generate_base64_png(self, data: str | bytes) -> str:
        """
        Генерирует QR‑код и возвращает изображение PNG в Base64.

        Если данные не помещаются в один QR‑код, они сжимаются zlib‑ом и
        кодируются base64 — это в большинстве случаев умещает полезную
        нагрузку без усложнения фронта.
        """
        if isinstance(data, str):
            payload = data.encode()
        else:
            payload = data

        qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
        try:
            qr.add_data(payload)
        except DataOverflowError:
            compressed = base64.b64encode(zlib.compress(payload))
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(compressed)

        qr.make(fit=True)
        img = qr.make_image()
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
