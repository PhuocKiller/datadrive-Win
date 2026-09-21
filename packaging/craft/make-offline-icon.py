"""Sinh icon DataDrive-offline.ico: logo mờ đi kèm huy hiệu X đỏ ở góc dưới phải.

Explorer hiện icon này trên mục điều hướng và thư mục đồng bộ khi tài khoản không kết nối
(xem src/gui/syncfoldershellstatus.cpp).

Chạy lại sau khi đổi logo:
    python packaging/craft/make-offline-icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance

REPO = Path(__file__).resolve().parents[2]
SOURCE = REPO / "Logo" / "Logo" / "png" / "datadrive-icon-512.png"
TARGET = REPO / "theme" / "colored" / "DataDrive-offline.ico"

ERROR_RED = (219, 6, 6, 255)
SIZE = 512


def main() -> None:
    logo = Image.open(SOURCE).convert("RGBA").resize((SIZE, SIZE), Image.LANCZOS)

    # Nhạt màu logo để đọc là "không hoạt động" ngay cả ở cỡ 16 px.
    faded = ImageEnhance.Color(logo).enhance(0.25)
    alpha = faded.getchannel("A").point(lambda a: int(a * 0.6))
    faded.putalpha(alpha)

    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas.alpha_composite(faded)

    # Huy hiệu tròn đỏ viền trắng, dấu X trắng.
    draw = ImageDraw.Draw(canvas)
    radius = int(SIZE * 0.24)
    ring = int(SIZE * 0.035)
    cx = cy = SIZE - radius - ring
    draw.ellipse((cx - radius - ring, cy - radius - ring, cx + radius + ring, cy + radius + ring), fill=(255, 255, 255, 255))
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=ERROR_RED)
    arm = int(radius * 0.5)
    width = int(SIZE * 0.055)
    draw.line((cx - arm, cy - arm, cx + arm, cy + arm), fill=(255, 255, 255, 255), width=width)
    draw.line((cx - arm, cy + arm, cx + arm, cy - arm), fill=(255, 255, 255, 255), width=width)

    canvas.save(TARGET, format="ICO", sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"da ghi {TARGET.relative_to(REPO)}")


if __name__ == "__main__":
    main()
