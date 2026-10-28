from io import BytesIO
from pathlib import Path
from uuid import uuid4
import os
import logging
import time
from urllib.parse import urlparse, unquote
import warnings

from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError
import cloudinary
import cloudinary.uploader
from cloudinary.utils import private_download_url


MAX_CHAT_IMAGES = 5
MAX_CHAT_IMAGE_BYTES = 10 * 1024 * 1024


class ChatUploadError(Exception):
    pass


def configure_chat_cloudinary():
    parsed = urlparse(os.getenv("CLOUDINARY_URL", ""))
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME") or parsed.hostname
    api_key = os.getenv("CLOUDINARY_API_KEY") or unquote(parsed.username or "")
    api_secret = os.getenv("CLOUDINARY_API_SECRET") or unquote(parsed.password or "")
    if not all((cloud_name, api_key, api_secret)) or api_key == "API_KEY" or api_secret == "API_SECRET":
        raise ChatUploadError("Cloudinary chưa được cấu hình đầy đủ. Vui lòng kiểm tra CLOUDINARY_URL trong .env.")
    cloudinary.config(cloud_name=cloud_name, api_key=api_key, api_secret=api_secret, secure=True)


def remove_chat_uploads(images):
    for image in images:
        try:
            cloudinary.uploader.destroy(image["public_id"], type="authenticated", resource_type="image")
        except Exception:
            logging.getLogger(__name__).warning("Could not remove a rolled-back chat image from Cloudinary")


def upload_chat_images(prepared, conversation_id):
    if not prepared:
        return []
    configure_chat_cloudinary()
    uploaded = []
    try:
        for file, name, mime in prepared:
            result = cloudinary.uploader.upload(
                file, resource_type="image", type="authenticated",
                folder=f"ql-phong-cho-thue/chat/{conversation_id}",
                public_id=uuid4().hex, overwrite=False, timeout=45,
            )
            uploaded.append({"public_id": result["public_id"], "format": result.get("format") or ("png" if mime == "image/png" else "jpg"),
                             "original_name": name, "content_type": mime})
    except Exception:
        remove_chat_uploads(uploaded)
        raise ChatUploadError("Chưa tải được ảnh lên Cloudinary. Vui lòng thử lại; ảnh và nội dung vẫn được giữ lại.")
    return uploaded


def chat_image_url(image):
    configure_chat_cloudinary()
    return private_download_url(image.public_id, image.format, type="authenticated", resource_type="image",
                                expires_at=int(time.time()) + 60, attachment=False, secure=True)


def prepare_chat_images(files):
    if len(files) > MAX_CHAT_IMAGES:
        raise ValidationError("Mỗi lần gửi tối đa 5 ảnh.")
    prepared = []
    for file in files:
        if file.size > MAX_CHAT_IMAGE_BYTES:
            raise ValidationError("Mỗi ảnh không được vượt quá 10 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(file)
                if image.format not in {"JPEG", "PNG", "WEBP"}:
                    raise ValidationError("Chỉ hỗ trợ ảnh JPG, PNG và WebP.")
                if image.width * image.height > 20_000_000:
                    raise ValidationError("Ảnh quá lớn. Vui lòng chọn ảnh dưới 20 megapixel.")
                image.load()
                from PIL import ImageOps
                image = ImageOps.exif_transpose(image)
                # Re-encode the image to strip metadata and any appended file data.
                output = BytesIO()
                if "A" in image.getbands() or "transparency" in image.info:
                    image.convert("RGBA").save(output, format="PNG")
                    filename, mime = "image.png", "image/png"
                else:
                    image.convert("RGB").save(output, format="JPEG", quality=90)
                    filename, mime = "image.jpg", "image/jpeg"
                if output.tell() > MAX_CHAT_IMAGE_BYTES:
                    raise ValidationError("Ảnh sau xử lý vượt quá 10 MB. Vui lòng chọn ảnh nhỏ hơn.")
                prepared.append((ContentFile(output.getvalue(), name=filename), Path(file.name).name[:255], mime))
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValidationError("Ảnh không hợp lệ hoặc bị hỏng. Vui lòng chọn ảnh JPG, PNG hoặc WebP khác.")
    return prepared
