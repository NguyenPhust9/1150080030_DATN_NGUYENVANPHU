import hashlib
import json
import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from apps.rentals.views import cloudinary_upload_signature


CLOUDINARY_ENV = {
    "CLOUDINARY_URL": "cloudinary://upload-key:upload-secret@room-cloud",
    "CLOUDINARY_CLOUD_NAME": "",
    "CLOUDINARY_API_KEY": "",
    "CLOUDINARY_API_SECRET": "",
}


@patch.dict(os.environ, CLOUDINARY_ENV)
class RoomUploadSignatureTests(SimpleTestCase):
    """Exercise upload authorization and signing without a database or uploads."""

    def setUp(self):
        self.factory = RequestFactory()
        self.url = reverse("cloudinary-upload-signature")
        # Unsaved users suffice: this endpoint must not need database queries.
        self.operator = get_user_model()(username="upload-owner", role="owner")

    def request(self, user=None, method="post", data=None):
        request = getattr(self.factory, method)(self.url, data=data or {})
        request.user = user if user is not None else self.operator
        return cloudinary_upload_signature(request)

    def test_anonymous_request_requires_login_and_does_not_sign(self):
        with patch("apps.rentals.views.api_sign_request") as sign:
            response = self.request(AnonymousUser())
        self.assertEqual(response.status_code, 302)
        self.assertIn("next=", response["Location"])
        sign.assert_not_called()

    def test_only_operators_may_request_upload_signatures(self):
        for role in ("tenant", "unknown"):
            with self.subTest(role=role), patch("apps.rentals.views.api_sign_request") as sign:
                with self.assertRaises(PermissionDenied):
                    self.request(get_user_model()(username="non-operator", role=role))
                sign.assert_not_called()
        for role in ("admin", "owner", "staff"):
            with self.subTest(role=role):
                response = self.request(get_user_model()(username="operator", role=role))
                self.assertEqual(response.status_code, 200)

    def test_signature_endpoint_rejects_get(self):
        with patch("apps.rentals.views.api_sign_request") as sign:
            response = self.request(method="get")
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response["Allow"], "POST")
        sign.assert_not_called()

    @patch("apps.rentals.views.time.time", return_value=1800000000.75)
    def test_signs_server_folder_and_timestamp_without_exposing_secret(self, current_time):
        response = self.request(data={"folder": "another-folder", "timestamp": "1"})
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        expected_signature = hashlib.sha1(
            b"folder=ql-phong-cho-thue/rooms&timestamp=1800000000upload-secret"
        ).hexdigest()
        self.assertEqual(data, {
            "timestamp": 1800000000,
            "folder": "ql-phong-cho-thue/rooms",
            "signature": expected_signature,
            "cloud_name": "room-cloud",
            "api_key": "upload-key",
        })
        self.assertNotIn("upload-secret", response.content.decode())
        self.assertNotIn("api_secret", data)
        self.assertIn("no-store", response["Cache-Control"])

    def test_separate_credentials_work_without_cloudinary_url(self):
        with patch.dict(os.environ, {
            "CLOUDINARY_URL": "",
            "CLOUDINARY_CLOUD_NAME": "separate-cloud",
            "CLOUDINARY_API_KEY": "separate-key",
            "CLOUDINARY_API_SECRET": "separate-secret",
        }), patch("apps.rentals.views.api_sign_request", return_value="signed") as sign:
            response = self.request()
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["cloud_name"], "separate-cloud")
        self.assertEqual(data["api_key"], "separate-key")
        self.assertEqual(sign.call_args.args[1], "separate-secret")
        self.assertNotIn("separate-secret", response.content.decode())

    def test_url_credentials_are_decoded(self):
        with patch.dict(os.environ, {
            "CLOUDINARY_URL": "cloudinary://upload%2Bkey:secret%2Fvalue@room-cloud",
        }), patch("apps.rentals.views.api_sign_request", return_value="signed") as sign:
            response = self.request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["api_key"], "upload+key")
        self.assertEqual(sign.call_args.args[1], "secret/value")

    def test_missing_config_returns_service_error_without_signing(self):
        separate_env = {
            "CLOUDINARY_URL": "",
            "CLOUDINARY_CLOUD_NAME": "room-cloud",
            "CLOUDINARY_API_KEY": "upload-key",
            "CLOUDINARY_API_SECRET": "upload-secret",
        }
        for missing_key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
            with self.subTest(missing_key=missing_key), patch.dict(
                os.environ, {**separate_env, missing_key: ""}
            ), patch("apps.rentals.views.api_sign_request") as sign:
                response = self.request()
                self.assertEqual(response.status_code, 503)
                self.assertIn("error", json.loads(response.content))
                self.assertIn("no-store", response["Cache-Control"])
                self.assertNotIn("upload-secret", response.content.decode())
                sign.assert_not_called()
