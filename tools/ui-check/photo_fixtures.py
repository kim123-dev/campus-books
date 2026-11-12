"""photo-check용 휴대폰 사진 흉내 파일을 실행할 때 만든다. (큰 파일을 저장소에 두지 않기 위해)

사용: python tools/ui-check/photo_fixtures.py <출력 폴더>
- large.jpg   6000x4500(2700만 화소) 책 표지 흉내: 글씨와 1px 선이 있어 줄였을 때 깨짐(물결무늬)이 잘 보인다.
- rotated.jpg 6000x4000 가로로 저장됐지만 EXIF 회전 값(6)이 있어 세로로 보여야 하는 사진
- motion.jpg  JPEG 안에 사진이 2장 든 MPO(갤럭시 울트라 HDR·움직이는 사진 흉내)
- photo.heic  아이폰 기본 형식. 헤드리스 크롬은 HEIC를 열지 못해 원본 그대로 서버로 보낸다.
"""

import sys
from pathlib import Path

import pillow_heif
from PIL import Image, ImageDraw, ImageFont

pillow_heif.register_heif_opener()


def book_cover(size: tuple[int, int]) -> Image.Image:
    """글씨·가는 선·색 면이 섞인 책 표지 그림. 같은 함수를 화질 비교에서도 기준 그림으로 쓴다."""
    width, height = size
    image = Image.new("RGB", size, (246, 242, 232))
    draw = ImageDraw.Draw(image)
    unit = width / 1000
    draw.rectangle([0, 0, width, int(180 * unit)], fill=(40, 70, 140))
    title = ImageFont.load_default(size=int(60 * unit))
    body = ImageFont.load_default(size=int(14 * unit))
    draw.text((int(40 * unit), int(50 * unit)), "Data Structures 3rd Ed.", font=title, fill=(255, 255, 255))
    for row in range(40):
        y = int((220 + row * 18) * unit)
        draw.text((int(40 * unit), y), f"{row:02d}  The quick brown fox jumps over the lazy dog 0123456789", font=body, fill=(30, 30, 30))
    # 1px 선: 크게 줄이면 사라지거나 물결무늬가 생기기 쉬운 부분
    for x in range(int(700 * unit), width - int(20 * unit), 6):
        draw.line([(x, int(220 * unit)), (x, int(700 * unit))], fill=(0, 0, 0), width=1)
    return image


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    book_cover((6000, 4500)).save(out / "large.jpg", quality=95)

    exif = Image.Exif()
    exif[0x0112] = 6  # 90도 돌려서 봐야 하는 사진
    rotated = Image.new("RGB", (6000, 4000), (200, 40, 40))
    ImageDraw.Draw(rotated).rectangle([0, 0, 3000, 4000], fill=(40, 40, 200))
    rotated.save(out / "rotated.jpg", quality=90, exif=exif.tobytes())

    first, second = book_cover((1600, 1200)), Image.new("RGB", (1600, 1200), (0, 0, 0))
    first.save(out / "motion.jpg", format="MPO", save_all=True, append_images=[second])

    book_cover((1200, 900)).save(out / "photo.heic", format="HEIF", quality=90)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
