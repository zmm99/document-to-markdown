from __future__ import annotations

from importlib import resources
from pathlib import Path

from app.config import settings
from app.converters.base import ConversionError


RAPIDOCR_MODEL_FILES = {
    "det_model_path": Path("onnx/PP-OCRv5/det/ch_PP-OCRv5_det_server.onnx"),
    "cls_model_path": Path("onnx/PP-OCRv5/cls/ch_PP-LCNet_x1_0_textline_ori_cls_server.onnx"),
    "rec_model_path": Path("onnx/PP-OCRv5/rec/ch_PP-OCRv5_rec_server.onnx"),
}
RAPIDOCR_MODEL_PROFILE = "PP-OCRv5-server-onnx"
RAPIDOCR_BITMAP_AREA_THRESHOLD = 0.05


def rapidocr_model_paths() -> dict[str, Path]:
    root = rapidocr_model_root()
    if root is None or not root.exists():
        raise ConversionError("ocr_model_missing", "RapidOCR model directory is not configured")

    paths: dict[str, Path] = {}
    for key, relative_path in RAPIDOCR_MODEL_FILES.items():
        path = root / relative_path
        if not path.exists():
            matches = list(root.rglob(relative_path.name))
            if matches:
                path = matches[0]
        if not path.exists():
            raise ConversionError(
                "ocr_model_missing",
                f"RapidOCR model file is missing: {relative_path.name}",
            )
        paths[key] = path.resolve()
    return paths


def rapidocr_model_root() -> Path | None:
    if settings.rapidocr_model_path is not None:
        return settings.rapidocr_model_path
    local_models = Path("models") / "rapidocr"
    if local_models.exists():
        return local_models
    return None


def rapidocr_rec_keys_path() -> str | None:
    try:
        keys = resources.files("rapidocr").joinpath("models", "ppocrv5_dict.txt")
    except (ModuleNotFoundError, AttributeError):
        return None
    if keys.is_file():
        return str(keys)
    return None


def rapidocr_params() -> dict[str, object]:
    from rapidocr import ModelType, OCRVersion

    params: dict[str, object] = {
        "Det.ocr_version": OCRVersion.PPOCRV5,
        "Det.model_type": ModelType.SERVER,
        "Cls.ocr_version": OCRVersion.PPOCRV5,
        "Cls.model_type": ModelType.SERVER,
        "Rec.ocr_version": OCRVersion.PPOCRV5,
        "Rec.model_type": ModelType.SERVER,
    }
    keys_path = rapidocr_rec_keys_path()
    if keys_path is not None:
        params["Rec.rec_keys_path"] = keys_path
    return params


def rapidocr_direct_params() -> dict[str, object]:
    model_paths = rapidocr_model_paths()
    return {
        **rapidocr_params(),
        "Det.model_path": str(model_paths["det_model_path"]),
        "Cls.model_path": str(model_paths["cls_model_path"]),
        "Rec.model_path": str(model_paths["rec_model_path"]),
    }
