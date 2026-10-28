import uuid
from io import BytesIO
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.rentals.models import Building, ChatMessage, Conversation, MessageReaction, ChatPresence, ChatImage, Room, Tenant
from config.asgi import application

User = get_user_model()


class ChatTests(TestCase):
    def setUp(self):
        self.owner1 = User.objects.create_user(username="chat_owner1", password="Password123!", role="owner")
        self.owner2 = User.objects.create_user(username="chat_owner2", password="Password123!", role="owner")
        self.tenant_user1 = User.objects.create_user(username="chat_tenant1", password="Password123!", role="tenant")
        self.tenant_user2 = User.objects.create_user(username="chat_tenant2", password="Password123!", role="tenant")
        self.building1 = Building.objects.create(name="Tòa chat 1", address="TP.HCM", owner=self.owner1)
        self.building2 = Building.objects.create(name="Tòa chat 2", address="Hà Nội", owner=self.owner2)
        Room.objects.create(building=self.building1, number="101", monthly_rent=Decimal("3000000"))
        Room.objects.create(building=self.building2, number="201", monthly_rent=Decimal("4000000"))
        self.tenant1 = Tenant.objects.create(
            owner=self.owner1,
            user=self.tenant_user1,
            full_name="Khách chat 1",
            phone="0901000001",
            identity_number="CHAT-ID-1",
        )
        self.tenant2 = Tenant.objects.create(
            owner=self.owner2,
            user=self.tenant_user2,
            full_name="Khách chat 2",
            phone="0902000002",
            identity_number="CHAT-ID-2",
        )

    def test_owner_starts_chat_only_with_tenant_in_scope(self):
        self.client.force_login(self.owner1)
        response = self.client.post(reverse("chat-start"), {"tenant_id": self.tenant1.pk, "subject": "Hợp đồng"})
        conversation = Conversation.objects.get(tenant=self.tenant1)
        self.assertRedirects(response, reverse("chat-detail", args=[conversation.pk]))
        self.assertTrue(conversation.participants.filter(pk=self.owner1.pk).exists())
        self.assertTrue(conversation.participants.filter(pk=self.tenant_user1.pk).exists())

        forbidden = self.client.post(reverse("chat-start"), {"tenant_id": self.tenant2.pk, "subject": "Không hợp lệ"})
        self.assertEqual(forbidden.status_code, 404)

    def test_tenant_can_send_and_other_tenant_cannot_read(self):
        conversation = Conversation.objects.create(tenant=self.tenant1, subject="Tiền phòng")
        conversation.participants.add(self.owner1, self.tenant_user1)
        self.client.force_login(self.tenant_user1)
        response = self.client.post(reverse("chat-send", args=[conversation.pk]), {"message": "Em đã chuyển khoản."})
        self.assertRedirects(response, reverse("chat-detail", args=[conversation.pk]))
        chat_message = ChatMessage.objects.get(conversation=conversation)
        self.assertEqual(chat_message.sender, self.tenant_user1)
        self.assertTrue(chat_message.read_by.filter(pk=self.tenant_user1.pk).exists())

        self.client.force_login(self.tenant_user2)
        self.assertEqual(self.client.get(reverse("chat-detail", args=[conversation.pk])).status_code, 404)

    def test_opening_conversation_marks_received_messages_read(self):
        conversation = Conversation.objects.create(tenant=self.tenant1, subject="Sửa chữa")
        conversation.participants.add(self.owner1, self.tenant_user1)
        message = ChatMessage.objects.create(conversation=conversation, sender=self.owner1, content="Đã nhận yêu cầu.")
        self.client.force_login(self.tenant_user1)
        self.assertEqual(self.client.get(reverse("chat-detail", args=[conversation.pk])).status_code, 200)
        self.assertTrue(message.read_by.filter(pk=self.tenant_user1.pk).exists())


    def test_json_send_and_incremental_updates_are_scoped(self):
        conversation = Conversation.objects.create(tenant=self.tenant1, subject="Live chat")
        self.client.force_login(self.owner1)
        response = self.client.post(
            reverse("chat-send", args=[conversation.pk]),
            {"message": "First message"}, HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        first_id = response.json()["message"]["id"]
        second = ChatMessage.objects.create(conversation=conversation, sender=self.owner1, content="Second message")
        self.client.force_login(self.tenant_user1)
        updates_url = reverse("chat-updates", args=[conversation.pk])
        response = self.client.get(updates_url, {"after": first_id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.json()["messages"]], [str(second.pk)])
        self.assertTrue(second.read_by.filter(pk=self.tenant_user1.pk).exists())
        self.assertEqual(self.client.get(updates_url, {"after": second.pk}).json()["messages"], [])
        self.assertEqual(self.client.get(updates_url, {"after": "invalid"}).status_code, 400)
        self.client.force_login(self.tenant_user2)
        self.assertEqual(self.client.get(updates_url).status_code, 404)


    def test_inbox_updates_include_other_threads_without_marking_read(self):
        conversation = Conversation.objects.create(tenant=self.tenant1, subject="Inbox")
        other = Conversation.objects.create(tenant=self.tenant2, subject="Private")
        first = ChatMessage.objects.create(conversation=conversation, sender=self.tenant_user1, content="Arrived while idle")
        ChatMessage.objects.create(conversation=other, sender=self.tenant_user2, content="Private message")
        self.client.force_login(self.owner1)
        response = self.client.get(reverse("chat-inbox-updates"))
        self.assertEqual(response.status_code, 200)
        items = response.json()["conversations"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], str(conversation.pk))
        self.assertEqual(items[0]["preview"], "Arrived while idle")
        self.assertEqual(items[0]["unread"], 1)
        self.assertFalse(first.read_by.filter(pk=self.owner1.pk).exists())


    def test_new_message_moves_thread_above_empty_and_older_threads(self):
        from django.utils import timezone
        from datetime import timedelta
        older = Conversation.objects.create(tenant=self.tenant1, subject="Older", last_message_at=timezone.now() - timedelta(hours=1))
        recent = Conversation.objects.create(tenant=self.tenant1, subject="Recent", last_message_at=timezone.now())
        empty = Conversation.objects.create(tenant=self.tenant1, subject="Empty")
        self.client.force_login(self.owner1)
        url = reverse("chat-inbox-updates")
        def ids():
            return [item["id"] for item in self.client.get(url).json()["conversations"]]
        self.assertEqual(ids(), [str(recent.pk), str(older.pk), str(empty.pk)])
        self.client.post(reverse("chat-send", args=[older.pk]), {"message": "Newest"}, HTTP_ACCEPT="application/json")
        self.assertEqual(ids(), [str(older.pk), str(recent.pk), str(empty.pk)])
        response = self.client.get(reverse("chat-list"))
        self.assertEqual([item.pk for item in response.context["conversations"]], [older.pk, recent.pk, empty.pk])


    def test_reactions_persist_toggle_change_and_sync_for_both_users(self):
        conversation = Conversation.objects.create(tenant=self.tenant1)
        message = ChatMessage.objects.create(conversation=conversation, sender=self.owner1, content="Hello \U0001f600")
        url = reverse("chat-react", args=[conversation.pk, message.pk])
        heart = "\u2764\ufe0f"
        like = "\U0001f44d"
        self.client.force_login(self.owner1)
        response = self.client.post(url, {"emoji": heart})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reactions"][0]["count"], 1)
        self.assertTrue(response.json()["reactions"][0]["mine"])
        self.client.force_login(self.tenant_user1)
        response = self.client.post(url, {"emoji": heart})
        self.assertEqual(response.json()["reactions"][0]["count"], 2)
        updates = self.client.get(reverse("chat-updates", args=[conversation.pk]), {"after": message.pk}).json()
        self.assertEqual(updates["messages"], [])
        self.assertEqual(updates["reactions"][str(message.pk)][0]["count"], 2)
        self.client.post(url, {"emoji": like})
        self.assertEqual(MessageReaction.objects.filter(message=message).count(), 2)
        self.assertEqual(MessageReaction.objects.get(message=message, user=self.tenant_user1).emoji, like)
        self.client.post(url, {"emoji": like})
        self.assertFalse(MessageReaction.objects.filter(message=message, user=self.tenant_user1).exists())
        self.client.force_login(self.owner1)
        self.assertEqual(self.client.post(url, {"emoji": heart}).json()["reactions"], [])

    def test_reactions_enforce_scope_valid_emoji_and_closed_thread(self):
        conversation = Conversation.objects.create(tenant=self.tenant1)
        message = ChatMessage.objects.create(conversation=conversation, sender=self.owner1, content="Private")
        other_conversation = Conversation.objects.create(tenant=self.tenant1)
        url = reverse("chat-react", args=[conversation.pk, message.pk])
        self.client.force_login(self.tenant_user2)
        self.assertEqual(self.client.post(url, {"emoji": "\U0001f44d"}).status_code, 404)
        self.client.force_login(self.owner1)
        self.assertEqual(self.client.post(url, {"emoji": "invalid"}).status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)
        wrong_url = reverse("chat-react", args=[other_conversation.pk, message.pk])
        self.assertEqual(self.client.post(wrong_url, {"emoji": "\U0001f44d"}).status_code, 404)
        conversation.is_closed = True
        conversation.save(update_fields=["is_closed"])
        self.assertEqual(self.client.post(url, {"emoji": "\U0001f44d"}).status_code, 404)
        self.assertEqual(MessageReaction.objects.count(), 0)


    def test_presence_handles_multiple_tabs_disconnects_and_stale_connections(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.rentals.chat_presence import presence_for_users
        now = timezone.now()
        first = ChatPresence.objects.create(connection="tab-one", user=self.tenant_user1)
        second = ChatPresence.objects.create(connection="tab-two", user=self.tenant_user1)
        def presence():
            return presence_for_users([self.tenant_user1.pk])[str(self.tenant_user1.pk)]
        self.assertTrue(presence()["online"])
        first.disconnected_at = now
        first.save(update_fields=["disconnected_at"])
        self.assertTrue(presence()["online"])
        second.disconnected_at = now
        second.save(update_fields=["disconnected_at"])
        self.assertFalse(presence()["online"])
        second.disconnected_at = None
        second.last_seen = now - timedelta(minutes=3)
        second.save(update_fields=["last_seen", "disconnected_at"])
        self.assertFalse(presence()["online"])
        self.client.force_login(self.owner1)
        conversation = Conversation.objects.create(tenant=self.tenant1)
        item = self.client.get(reverse("chat-inbox-updates")).json()["conversations"][0]
        self.assertFalse(item["presence"]["online"])
        second.last_seen = now
        second.save(update_fields=["last_seen"])
        item = self.client.get(reverse("chat-inbox-updates")).json()["conversations"][0]
        self.assertTrue(item["presence"]["online"])


    @staticmethod
    def chat_picture(name="photo.png"):
        buffer = BytesIO()
        Image.new("RGBA", (12, 10), (120, 80, 200, 255)).save(buffer, format="PNG")
        return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")

    def test_cloudinary_image_only_message_and_private_delivery(self):
        conversation = Conversation.objects.create(tenant=self.tenant1)
        self.client.force_login(self.owner1)
        with patch("apps.rentals.chat_media.configure_chat_cloudinary"), patch("apps.rentals.chat_media.cloudinary.uploader.upload", return_value={"public_id": "chat/test-photo", "format": "png"}) as upload:
            response = self.client.post(reverse("chat-send", args=[conversation.pk]), {"images": [self.chat_picture()]}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        payload = response.json()["message"]
        self.assertEqual(payload["content"], "")
        self.assertEqual(len(payload["images"]), 1)
        self.assertEqual(upload.call_args.kwargs["type"], "authenticated")
        self.assertEqual(upload.call_args.kwargs["resource_type"], "image")
        image = ChatImage.objects.get()
        self.assertEqual(image.public_id, "chat/test-photo")
        image_url = payload["images"][0]["url"]
        with patch("apps.rentals.chat_media.configure_chat_cloudinary"), patch("apps.rentals.chat_media.private_download_url", return_value="https://api.cloudinary.com/test/download?signed=1") as signed:
            self.assertEqual(self.client.get(image_url).status_code, 302)
            self.assertFalse(signed.call_args.kwargs["attachment"])
            self.assertEqual(signed.call_args.kwargs["type"], "authenticated")
        self.client.force_login(self.tenant_user1)
        updates = self.client.get(reverse("chat-updates", args=[conversation.pk])).json()
        self.assertEqual(updates["messages"][0]["images"][0]["url"], image_url)
        self.assertEqual(self.client.get(reverse("chat-inbox-updates")).json()["conversations"][0]["preview"], "\U0001f4f7 H\u00ecnh \u1ea3nh")
        self.assertContains(self.client.get(reverse("chat-detail", args=[conversation.pk])), image_url)
        self.client.force_login(self.tenant_user2)
        self.assertEqual(self.client.get(image_url).status_code, 404)

    def test_invalid_images_are_rejected_before_upload(self):
        conversation = Conversation.objects.create(tenant=self.tenant1)
        self.client.force_login(self.owner1)
        url = reverse("chat-send", args=[conversation.pk])
        with patch("apps.rentals.chat_media.cloudinary.uploader.upload") as upload:
            invalid = SimpleUploadedFile("fake.png", b"<svg>Not a raster image</svg>", content_type="image/png")
            self.assertEqual(self.client.post(url, {"images": [invalid]}, HTTP_ACCEPT="application/json").status_code, 400)
            self.assertEqual(self.client.post(url, {"images": [self.chat_picture() for _ in range(6)]}, HTTP_ACCEPT="application/json").status_code, 400)
            self.client.force_login(self.tenant_user2)
            self.assertEqual(self.client.post(url, {"images": [self.chat_picture()]}, HTTP_ACCEPT="application/json").status_code, 404)
            upload.assert_not_called()
        self.assertFalse(ChatMessage.objects.exists())

    def test_partial_cloudinary_failure_rolls_back_uploads_and_message(self):
        conversation = Conversation.objects.create(tenant=self.tenant1)
        self.client.force_login(self.owner1)
        with patch("apps.rentals.chat_media.configure_chat_cloudinary"), patch("apps.rentals.chat_media.cloudinary.uploader.upload", side_effect=[{"public_id": "chat/first", "format": "png"}, RuntimeError("service unavailable")]), patch("apps.rentals.chat_media.cloudinary.uploader.destroy") as destroy:
            response = self.client.post(reverse("chat-send", args=[conversation.pk]), {"message": "Photos", "images": [self.chat_picture(), self.chat_picture("second.png")]}, HTTP_ACCEPT="application/json")
            self.assertEqual(response.status_code, 502)
            destroy.assert_called_once_with("chat/first", type="authenticated", resource_type="image")
        self.assertFalse(ChatMessage.objects.exists())
        self.assertFalse(ChatImage.objects.exists())

    def test_image_caption_and_missing_cloudinary_configuration(self):
        from apps.rentals.chat_media import ChatUploadError
        conversation = Conversation.objects.create(tenant=self.tenant1)
        self.client.force_login(self.owner1)
        url = reverse("chat-send", args=[conversation.pk])
        with patch("apps.rentals.chat_media.configure_chat_cloudinary", side_effect=ChatUploadError("Cloudinary not configured")):
            self.assertEqual(self.client.post(url, {"images": [self.chat_picture()]}, HTTP_ACCEPT="application/json").status_code, 502)
        self.assertFalse(ChatMessage.objects.exists())
        with patch("apps.rentals.chat_media.configure_chat_cloudinary"), patch("apps.rentals.chat_media.cloudinary.uploader.upload", return_value={"public_id": "chat/caption", "format": "png"}):
            response = self.client.post(url, {"message": "Photo caption", "images": [self.chat_picture()]}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["message"]["content"], "Photo caption")
        self.assertEqual(ChatImage.objects.count(), 1)


class ChatWebSocketTests(TransactionTestCase):
    def setUp(self):
        suffix = uuid.uuid4().hex[:8]
        self.owner = User.objects.create_user(username=f"ws_owner_{suffix}", password="Password123!", role="owner")
        self.tenant_user = User.objects.create_user(username=f"ws_tenant_{suffix}", password="Password123!", role="tenant")
        self.tenant = Tenant.objects.create(
            owner=self.owner,
            user=self.tenant_user,
            full_name="Khách WebSocket",
            phone="0903000001",
            identity_number=f"CHAT-WS-{suffix}",
        )
        self.conversation = Conversation.objects.create(tenant=self.tenant, subject="WebSocket")
        self.conversation.participants.add(self.owner, self.tenant_user)

    def test_authenticated_websocket_delivers_and_persists_message(self):
        self.client.force_login(self.tenant_user)
        session_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        receiver_client = Client()
        receiver_client.force_login(self.owner)
        receiver_cookie = receiver_client.cookies[settings.SESSION_COOKIE_NAME].value
        payload = async_to_sync(self._roundtrip)(session_cookie, receiver_cookie)
        self.assertEqual(payload["type"], "message")
        self.assertEqual(payload["content"], "Tin nhắn thời gian thực")
        self.assertTrue(
            ChatMessage.objects.filter(
                conversation=self.conversation,
                sender=self.tenant_user,
                content="Tin nhắn thời gian thực",
            ).exists()
        )


    def test_call_signals_are_delivered_only_to_authorized_peer(self):
        self.client.force_login(self.owner)
        owner_cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        peer_client = Client()
        peer_client.force_login(self.tenant_user)
        peer_cookie = peer_client.cookies[settings.SESSION_COOKIE_NAME].value
        outsider = User.objects.create_user(username="call_outsider", password="Password123!", role="tenant")
        async_to_sync(self._call_signals)(owner_cookie, peer_cookie, outsider.pk)

    async def _call_signals(self, owner_cookie, peer_cookie, outsider_id):
        def client(cookie):
            return WebsocketCommunicator(application, "/ws/chat/inbox/", headers=[
                (b"host", b"localhost"), (b"origin", b"http://localhost"),
                (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode()),
            ])
        owner, peer = client(owner_cookie), client(peer_cookie)
        self.assertTrue((await owner.connect())[0])
        self.assertTrue((await peer.connect())[0])
        self.assertEqual((await owner.receive_json_from(timeout=2))["type"], "presence.updated")
        call_id = str(uuid.uuid4())
        payload = {"type": "call.signal", "conversation_id": str(self.conversation.pk),
                   "target_id": str(self.tenant_user.pk), "call_id": call_id, "media": "video",
                   "action": "offer", "description": {"type": "offer", "sdp": "test-offer"},
                   "sender_id": str(outsider_id)}
        await owner.send_json_to(payload)
        offer = await peer.receive_json_from(timeout=2)
        self.assertEqual(offer["sender_id"], str(self.owner.pk))
        self.assertEqual(offer["call_id"], call_id)
        self.assertEqual(offer["description"]["sdp"], "test-offer")
        reply = {**payload, "target_id": str(self.owner.pk), "action": "answer",
                 "description": {"type": "answer", "sdp": "test-answer"}}
        await peer.send_json_to(reply)
        self.assertEqual((await owner.receive_json_from(timeout=2))["action"], "answer")
        await owner.send_json_to({**payload, "action": "hangup"})
        self.assertEqual((await peer.receive_json_from(timeout=2))["action"], "hangup")
        await owner.send_json_to({**payload, "target_id": str(outsider_id)})
        self.assertEqual((await owner.receive_json_from(timeout=2))["type"], "call.error")
        await owner.send_json_to({**payload, "conversation_id": str(uuid.uuid4())})
        self.assertEqual((await owner.receive_json_from(timeout=2))["type"], "call.error")
        self.assertTrue(await peer.receive_nothing(timeout=0.1))
        await owner.disconnect()
        await peer.disconnect()


    def test_inbox_connect_disconnect_updates_presence(self):
        self.client.force_login(self.tenant_user)
        cookie = self.client.cookies[settings.SESSION_COOKIE_NAME].value
        async_to_sync(self._presence_lifecycle)(cookie)

    async def _presence_lifecycle(self, cookie):
        from channels.db import database_sync_to_async
        from apps.rentals.chat_presence import presence_for_users
        def client():
            return WebsocketCommunicator(application, "/ws/chat/inbox/", headers=[
                (b"host", b"localhost"), (b"origin", b"http://localhost"),
                (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode()),
            ])
        async def online():
            result = await database_sync_to_async(presence_for_users)([self.tenant_user.pk])
            return result.get(str(self.tenant_user.pk), {}).get("online", False)
        first, second = client(), client()
        self.assertTrue((await first.connect())[0])
        self.assertTrue((await second.connect())[0])
        self.assertTrue(await online())
        await first.disconnect()
        self.assertTrue(await online())
        await second.send_json_to({"type": "presence.ping"})
        self.assertTrue(await online())
        await second.disconnect()
        self.assertFalse(await online())

    async def _roundtrip(self, session_cookie, receiver_cookie):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conversation.pk}/",
            headers=[
                (b"host", b"localhost"),
                (b"origin", b"http://localhost"),
                (b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode()),
            ],
        )
        inbox = WebsocketCommunicator(
            application,
            "/ws/chat/inbox/",
            headers=[
                (b"host", b"localhost"),
                (b"origin", b"http://localhost"),
                (b"cookie", f"{settings.SESSION_COOKIE_NAME}={receiver_cookie}".encode()),
            ],
        )
        inbox_connected, _ = await inbox.connect()
        self.assertTrue(inbox_connected)
        receiver = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conversation.pk}/",
            headers=[
                (b"host", b"localhost"),
                (b"origin", b"http://localhost"),
                (b"cookie", f"{settings.SESSION_COOKIE_NAME}={receiver_cookie}".encode()),
            ],
        )
        receiver_connected, _ = await receiver.connect()
        self.assertTrue(receiver_connected)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.send_json_to({"message": "Tin nhắn thời gian thực"})
        response = await communicator.receive_json_from(timeout=2)
        received = await receiver.receive_json_from(timeout=2)
        self.assertEqual(received, response)
        inbox_event = await inbox.receive_json_from(timeout=2)
        self.assertEqual(inbox_event, {"type": "inbox.updated"})
        from channels.layers import get_channel_layer
        await get_channel_layer().group_send(f"chat-{self.conversation.pk}", {"type": "chat.reaction"})
        self.assertEqual(await receiver.receive_json_from(timeout=2), {"type": "reactions.updated"})
        self.assertEqual(await inbox.receive_json_from(timeout=2), {"type": "inbox.updated"})
        await inbox.disconnect()
        await inbox.wait(timeout=2)
        await receiver.disconnect()
        await receiver.wait(timeout=2)
        await communicator.disconnect()
        await communicator.wait(timeout=2)
        return response
