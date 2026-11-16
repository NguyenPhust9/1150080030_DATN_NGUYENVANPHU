"""Persistent avatar storage for serverless deployments."""
import os
from urllib.parse import unquote, urlparse
from uuid import uuid4

import cloudinary.uploader
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


class AvatarUploadError(Exception):
    pass


@deconstructible
class AvatarStorage(FileSystemStorage):
    def _save(self, name, content):
        if not settings.AVATAR_USE_CLOUDINARY:
            try:
                return super()._save(name, content)
            except OSError as exc:
                raise AvatarUploadError("Không lưu được ảnh đại diện. Vui lòng thử lại.") from exc
        parsed = urlparse(os.getenv("CLOUDINARY_URL", ""))
        credentials = {
            "cloud_name": os.getenv("CLOUDINARY_CLOUD_NAME") or parsed.hostname,
            "api_key": os.getenv("CLOUDINARY_API_KEY") or unquote(parsed.username or ""),
            "api_secret": os.getenv("CLOUDINARY_API_SECRET") or unquote(parsed.password or ""),
        }
        if not all(credentials.values()):
            raise AvatarUploadError("Chưa cấu hình đầy đủ Cloudinary để lưu ảnh đại diện.")
        try:
            content.seek(0)
            result = cloudinary.uploader.upload(
                content, **credentials, resource_type="image", type="upload",
                public_id=f"ql-phong-cho-thue/avatars/{uuid4().hex}",
                overwrite=False, timeout=30,
            )
            url = result["secure_url"]
            parsed_url = urlparse(url)
            if parsed_url.scheme != "https" or parsed_url.hostname != "res.cloudinary.com" or len(url) > 500:
                raise ValueError("Invalid Cloudinary image URL")
            return url
        except Exception as exc:
            raise AvatarUploadError("Chưa tải được ảnh đại diện lên Cloudinary. Vui lòng thử lại.") from exc

    def url(self, name):
        if name.startswith("https://res.cloudinary.com/"):
            return name
        return super().url(name)
