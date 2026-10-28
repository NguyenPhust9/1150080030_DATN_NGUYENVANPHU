from channels.db import database_sync_to_async
import json
from uuid import UUID
from datetime import timedelta
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from .models import ChatMessage, Conversation, ChatPresence
from .permissions import get_accessible_conversations


class InboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.groups_joined = []
        user = self.scope["user"]
        if not user.is_authenticated:
            await self.close(code=4403)
            return
        for conversation_id in await self._conversation_ids(user):
            group = f"chat-{conversation_id}"
            await self.channel_layer.group_add(group, self.channel_name)
            self.groups_joined.append(group)
        self.call_group = f"calls-{user.pk}"
        await self.channel_layer.group_add(self.call_group, self.channel_name)
        self.groups_joined.append(self.call_group)
        await self.accept()
        await self._touch_presence()
        await self._notify_presence()

    @database_sync_to_async
    def _conversation_ids(self, user):
        return list(get_accessible_conversations(user).values_list("id", flat=True))

    async def disconnect(self, close_code):
        if getattr(self, "call_group", None):
            await self._leave_presence()
            await self._notify_presence()
        for group in getattr(self, "groups_joined", []):
            await self.channel_layer.group_discard(group, self.channel_name)

    async def chat_message(self, event):
        # Only invalidate the inbox; the HTTP endpoint checks current permissions.
        await self.send_json({"type": "inbox.updated"})

    async def chat_reaction(self, event):
        await self.send_json({"type": "inbox.updated"})

    @database_sync_to_async
    def _touch_presence(self):
        now = timezone.now()
        ChatPresence.objects.update_or_create(connection=self.channel_name, defaults={
            "user": self.scope["user"], "last_seen": now, "disconnected_at": None,
        })
        ChatPresence.objects.filter(last_seen__lt=now - timedelta(days=7)).delete()

    @database_sync_to_async
    def _leave_presence(self):
        now = timezone.now()
        ChatPresence.objects.filter(connection=self.channel_name).update(last_seen=now, disconnected_at=now)

    async def _notify_presence(self):
        for group in getattr(self, "groups_joined", []):
            if group.startswith("chat-"):
                await self.channel_layer.group_send(group, {"type": "presence.changed", "user_id": str(self.scope["user"].pk)})

    async def presence_changed(self, event):
        if event.get("user_id") != str(self.scope["user"].pk):
            await self.send_json({"type": "presence.updated"})

    async def receive_json(self, content, **kwargs):
        if content.get("type") == "presence.ping":
            await self._touch_presence()
            return
        if content.get("type") != "call.signal":
            return
        try:
            conversation_id = UUID(content.get("conversation_id", ""))
            target_id = UUID(content.get("target_id", ""))
            call_id = str(UUID(content.get("call_id", "")))
        except (ValueError, TypeError, AttributeError):
            await self.send_json({"type": "call.error", "message": "Cuộc gọi không hợp lệ."})
            return
        action = content.get("action")
        if action not in {"offer", "answer", "ice", "reject", "hangup", "busy"} or len(json.dumps(content)) > 65000:
            return
        if not await self._can_call(conversation_id, target_id):
            await self.send_json({"type": "call.error", "message": "Không thể gọi tài khoản này."})
            return
        payload = {
            "type": "call.signal", "action": action, "call_id": call_id,
            "conversation_id": str(conversation_id), "sender_id": str(self.scope["user"].pk),
            "sender_name": self.scope["user"].get_full_name() or self.scope["user"].username,
            "media": "video" if content.get("media") == "video" else "audio",
        }
        if action in {"offer", "answer"}:
            description = content.get("description", {})
            if not isinstance(description, dict) or description.get("type") != action or not isinstance(description.get("sdp"), str) or len(description["sdp"]) > 50000:
                return
            payload["description"] = {"type": action, "sdp": description["sdp"]}
        if action == "ice":
            candidate = content.get("candidate")
            if not isinstance(candidate, dict) or len(json.dumps(candidate)) > 5000:
                return
            payload["candidate"] = candidate
        await self.channel_layer.group_send(f"calls-{target_id}", {"type": "call.signal", "payload": payload})

    @database_sync_to_async
    def _can_call(self, conversation_id, target_id):
        from django.contrib.auth import get_user_model
        user = self.scope["user"]
        if user.pk == target_id or not get_accessible_conversations(user).filter(pk=conversation_id, is_closed=False).exists():
            return False
        target = get_user_model().objects.filter(pk=target_id, is_active=True).first()
        return bool(target and get_accessible_conversations(target).filter(pk=conversation_id, is_closed=False).exists())

    async def call_signal(self, event):
        await self.send_json(event["payload"])


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

    async def chat_reaction(self, event):
        await self.send_json({"type": "reactions.updated"})

    async def presence_changed(self, event):
        pass

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
            "images": [],
        }
