from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import ChatMessage, Conversation
from .permissions import get_accessible_conversations


class ChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        self.group_name = f"chat-{self.conversation_id}"
        if not self.user.is_authenticated or not await self._can_access():
            await self.close(code=4403)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self._join_and_mark_read()

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        text = str(content.get("message", "")).strip()
        if not text or len(text) > 4000:
            await self.send_json({"type": "error", "message": "Tin nhắn phải có từ 1 đến 4.000 ký tự."})
            return
        message = await self._save_message(text)
        await self.channel_layer.group_send(self.group_name, {"type": "chat.message", "message": message})

    async def chat_message(self, event):
        await self.send_json({"type": "message", **event["message"]})

    @database_sync_to_async
    def _can_access(self):
        return get_accessible_conversations(self.user).filter(pk=self.conversation_id, is_closed=False).exists()

    @database_sync_to_async
    def _join_and_mark_read(self):
        conversation = Conversation.objects.get(pk=self.conversation_id)
        conversation.participants.add(self.user)
        unread = conversation.chat_messages.exclude(sender=self.user).exclude(read_by=self.user)
        through = ChatMessage.read_by.through
        through.objects.bulk_create(
            [through(chatmessage_id=message_id, user_id=self.user.pk) for message_id in unread.values_list("id", flat=True)],
            ignore_conflicts=True,
        )

    @database_sync_to_async
    def _save_message(self, text):
        conversation = Conversation.objects.get(pk=self.conversation_id, is_closed=False)
        message = ChatMessage.objects.create(conversation=conversation, sender=self.user, content=text)
        message.read_by.add(self.user)
        conversation.participants.add(self.user)
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=("last_message_at", "updated_at"))
        return {
            "id": str(message.pk),
            "content": message.content,
            "sender_id": str(self.user.pk),
            "sender_name": self.user.get_full_name() or self.user.username,
            "created_at": timezone.localtime(message.created_at).strftime("%H:%M %d/%m/%Y"),
        }
