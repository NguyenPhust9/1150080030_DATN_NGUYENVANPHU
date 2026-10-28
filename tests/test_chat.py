import uuid
from decimal import Decimal

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from apps.rentals.models import Building, ChatMessage, Conversation, Room, Tenant
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
        payload = async_to_sync(self._roundtrip)(session_cookie)
        self.assertEqual(payload["type"], "message")
        self.assertEqual(payload["content"], "Tin nhắn thời gian thực")
        self.assertTrue(
            ChatMessage.objects.filter(
                conversation=self.conversation,
                sender=self.tenant_user,
                content="Tin nhắn thời gian thực",
            ).exists()
        )

    async def _roundtrip(self, session_cookie):
        communicator = WebsocketCommunicator(
            application,
            f"/ws/chat/{self.conversation.pk}/",
            headers=[
                (b"host", b"localhost"),
                (b"origin", b"http://localhost"),
                (b"cookie", f"{settings.SESSION_COOKIE_NAME}={session_cookie}".encode()),
            ],
        )
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        await communicator.send_json_to({"message": "Tin nhắn thời gian thực"})
        response = await communicator.receive_json_from(timeout=2)
        await communicator.disconnect()
        await communicator.wait(timeout=2)
        return response
