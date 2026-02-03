import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from image_tool import (
    convert_image,
    crop_image,
    generate_image,
    get_images_dir,
    resize_image,
    safe_resolve_path,
    validate_image_filename,
)

image_router = APIRouter()
get_images_dir()


class GenerateImageRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    negative_prompt: str | None = None
    width: int = 1024
    height: int = 1024
    num_images: int = 1
    seed: int | None = None
    model: str | None = None


class ResizeImageRequest(BaseModel):
    input_filename: str
    width: int
    height: int
    mode: str = "contain"
    output_filename: str | None = None


class CropImageRequest(BaseModel):
    input_filename: str
    x: int
    y: int
    width: int
    height: int
    output_filename: str | None = None


class ConvertImageRequest(BaseModel):
    input_filename: str
    format: str
    quality: int | None = None
    output_filename: str | None = None


@image_router.post("/tools/generate_image")
def generate_image_route(body: GenerateImageRequest) -> dict:
    try:
        return generate_image(
            prompt=body.prompt,
            negative_prompt=body.negative_prompt,
            width=body.width,
            height=body.height,
            num_images=body.num_images,
            seed=body.seed,
            model=body.model or "gemini-image-2",
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@image_router.post("/tools/resize_image")
def resize_image_route(body: ResizeImageRequest) -> dict:
    try:
        return resize_image(
            input_filename=body.input_filename,
            width=body.width,
            height=body.height,
            mode=body.mode,
            output_filename=body.output_filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@image_router.post("/tools/crop_image")
def crop_image_route(body: CropImageRequest) -> dict:
    try:
        return crop_image(
            input_filename=body.input_filename,
            x=body.x,
            y=body.y,
            width=body.width,
            height=body.height,
            output_filename=body.output_filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@image_router.post("/tools/convert_image")
def convert_image_route(body: ConvertImageRequest) -> dict:
    try:
        return convert_image(
            input_filename=body.input_filename,
            format=body.format,
            quality=body.quality,
            output_filename=body.output_filename,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@image_router.get("/images/{filename}")
def get_image(filename: str) -> FileResponse:
    try:
        safe_name = validate_image_filename(filename)
        path = safe_resolve_path(safe_name)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Image not found.")
        media_type, _ = mimetypes.guess_type(path.name)
        return FileResponse(path, media_type=media_type or "application/octet-stream", filename=path.name)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Failed to read image.") from exc
