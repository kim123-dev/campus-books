// 올리기 전에 휴대폰 사진을 브라우저에서 줄인다.
// 휴대폰 원본(1200만~2억 화소, 5~20MB)을 그대로 보내면 느리고 데이터도 많이 쓴다.
// 서버는 어차피 긴 변 1600px WebP로 다시 만들므로, 그보다 큰 크기까지만 줄여 보낸다.
//
// 정확히 절반씩만 줄이는 이유: 브라우저(canvas)는 2000px처럼 임의 크기로 줄이면 책 글씨·가는 선에
// 물결무늬가 생겼다(최종 사진 PSNR 39 → 33dB). 절반으로 줄이기는 2x2 픽셀 평균이라 깨끗하고,
// 마지막 1600px 축소는 서버(Pillow Lanczos)가 한다. 이렇게 하면 원본을 그대로 보낼 때와 화질이 같다(39.0 vs 39.1dB).

/** 긴 변이 이 값 아래로 내려가지 않는 데까지만 절반씩 줄인다. (결과는 2000~3999px) */
export const RESIZE_MIN_SIDE = 2000;
export const RESIZE_QUALITY = 0.9;
// 줄일 필요가 없는 사진은 서버가 받는 형식·용량이면 원본 그대로 보낸다. (화질 손실을 한 번 줄인다)
const KEEP_TYPES = ["image/jpeg", "image/png", "image/webp"];
const KEEP_MAX_BYTES = 25 * 1024 * 1024;

/**
 * 사진 한 장을 올리기 좋게 바꾼다.
 * @param {File} file
 * @returns {Promise<{file: File, previewable: boolean}>}
 *   previewable이 false면 이 브라우저가 열 수 없는 사진(예: 안드로이드 크롬의 HEIC)이라 원본을 그대로 돌려준다.
 *   그런 사진은 서버가 직접 열어 변환한다.
 */
export async function preparePhoto(file) {
  let bitmap;
  try {
    // 휴대폰 사진의 회전 정보(EXIF)를 반영해 똑바로 선 그림으로 연다.
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    return { file, previewable: false };
  }

  try {
    let width = bitmap.width;
    let height = bitmap.height;
    const halvings = Math.max(0, Math.floor(Math.log2(Math.max(width, height) / RESIZE_MIN_SIDE)));
    if (halvings === 0 && KEEP_TYPES.includes(file.type) && file.size <= KEEP_MAX_BYTES) {
      return { file, previewable: true };
    }

    // 절반씩 여러 번 줄인다. 한 번에 1/4로 줄이면 다시 물결무늬가 생기기 때문이다.
    // 첫 단계부터 원본 bitmap을 절반으로 그려, 원본 크기의 캔버스를 만들지 않는다.
    // (아이폰 Safari는 약 1670만 화소보다 큰 캔버스를 그리지 못한다)
    // 줄일 필요는 없지만 형식·용량 때문에 바꿔야 하는 사진(halvings가 0)은 같은 크기로 JPEG만 만든다.
    let canvas = null;
    for (let step = 0; step < Math.max(1, halvings); step++) {
      if (halvings > 0) {
        width = Math.max(1, Math.round(width / 2));
        height = Math.max(1, Math.round(height / 2));
      }
      canvas = drawScaled(canvas ?? bitmap, width, height, step === 0);
    }

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", RESIZE_QUALITY));
    // 메모리가 부족한 휴대폰에서는 만들기에 실패할 수 있다. 그때는 원본을 보내고 서버에 맡긴다.
    if (!blob) return { file, previewable: true };
    const name = `${file.name.replace(/\.[^.]*$/, "") || "photo"}.jpg`;
    return { file: new File([blob], name, { type: "image/jpeg" }), previewable: true };
  } catch {
    return { file, previewable: true };
  } finally {
    bitmap.close(); // 큰 사진의 픽셀 메모리를 바로 놓아준다.
  }
}

/** source를 width x height 캔버스에 그린다. whiteBackground면 투명한 부분을 흰색으로 채운다. (JPEG에는 투명도가 없다) */
function drawScaled(source, width, height, whiteBackground) {
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (whiteBackground) {
    context.fillStyle = "#fff";
    context.fillRect(0, 0, width, height);
  }
  context.imageSmoothingQuality = "high";
  context.drawImage(source, 0, 0, width, height);
  return canvas;
}
