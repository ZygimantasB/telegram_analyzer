import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
    FloodWaitError,
)
from django.conf import settings


class TelegramClientManager:
    """Manager class for handling Telethon client operations."""

    def __init__(self):
        self.api_id = settings.TELEGRAM_API_ID
        self.api_hash = settings.TELEGRAM_API_HASH
        self._clients = {}

    def _get_event_loop(self):
        """Get or create event loop."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop

    def get_client(self, session_string=None):
        """Create a new Telegram client."""
        if session_string:
            session = StringSession(session_string)
        else:
            session = StringSession()
        return TelegramClient(session, self.api_id, self.api_hash)

    async def _send_code_async(self, client, phone_number):
        """Send verification code to phone number."""
        await client.connect()
        result = await client.send_code_request(phone_number)
        return result

    def send_code(self, phone_number):
        """Synchronous wrapper to send verification code."""
        loop = self._get_event_loop()
        client = self.get_client()

        async def _send():
            try:
                await client.connect()
                result = await client.send_code_request(phone_number)
                session_string = client.session.save()
                return {
                    'success': True,
                    'phone_code_hash': result.phone_code_hash,
                    'session_string': session_string,
                }
            except FloodWaitError as e:
                return {
                    'success': False,
                    'error': f'Too many attempts. Please wait {e.seconds} seconds.',
                    'flood_wait': e.seconds,
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                }
            finally:
                await client.disconnect()

        return loop.run_until_complete(_send())

    def verify_code(self, session_string, phone_number, phone_code_hash, code):
        """Verify the code sent to phone."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _verify():
            try:
                await client.connect()
                await client.sign_in(
                    phone=phone_number,
                    code=code,
                    phone_code_hash=phone_code_hash
                )
                me = await client.get_me()
                new_session_string = client.session.save()
                return {
                    'success': True,
                    'session_string': new_session_string,
                    'user_id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                    'requires_2fa': False,
                }
            except SessionPasswordNeededError:
                new_session_string = client.session.save()
                return {
                    'success': True,
                    'requires_2fa': True,
                    'session_string': new_session_string,
                }
            except PhoneCodeInvalidError:
                return {
                    'success': False,
                    'error': 'Invalid verification code. Please try again.',
                }
            except PhoneCodeExpiredError:
                return {
                    'success': False,
                    'error': 'Verification code expired. Please request a new one.',
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                }
            finally:
                await client.disconnect()

        return loop.run_until_complete(_verify())

    def verify_2fa(self, session_string, password):
        """Verify 2FA password."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _verify_2fa():
            try:
                await client.connect()
                await client.sign_in(password=password)
                me = await client.get_me()
                new_session_string = client.session.save()
                return {
                    'success': True,
                    'session_string': new_session_string,
                    'user_id': me.id,
                    'username': me.username,
                    'first_name': me.first_name,
                    'last_name': me.last_name,
                }
            except PasswordHashInvalidError:
                return {
                    'success': False,
                    'error': 'Invalid 2FA password. Please try again.',
                }
            except Exception as e:
                return {
                    'success': False,
                    'error': str(e),
                }
            finally:
                await client.disconnect()

        return loop.run_until_complete(_verify_2fa())

    def disconnect_session(self, session_string):
        """Disconnect and logout from Telegram."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _disconnect():
            try:
                await client.connect()
                await client.log_out()
                return {'success': True}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_disconnect())

    def get_dialogs(self, session_string, limit=100):
        """Get user's dialogs/chats."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _get_dialogs():
            try:
                await client.connect()
                dialogs = await client.get_dialogs(limit=limit)
                result = []
                for dialog in dialogs:
                    entity = dialog.entity
                    chat_type = 'user'
                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        chat_type = 'supergroup'
                    elif hasattr(entity, 'broadcast') and entity.broadcast:
                        chat_type = 'channel'
                    elif hasattr(entity, 'gigagroup') and entity.gigagroup:
                        chat_type = 'supergroup'
                    elif hasattr(entity, 'participants_count'):
                        chat_type = 'group'

                    result.append({
                        'id': dialog.id,
                        'title': dialog.title or dialog.name,
                        'type': chat_type,
                        'username': getattr(entity, 'username', None),
                        'unread_count': dialog.unread_count,
                        'is_archived': dialog.archived,
                    })
                return {'success': True, 'dialogs': result}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_get_dialogs())

    def check_session(self, session_string):
        """Check if session is still valid."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _check():
            try:
                await client.connect()
                if await client.is_user_authorized():
                    me = await client.get_me()
                    return {
                        'success': True,
                        'is_valid': True,
                        'user_id': me.id,
                        'username': me.username,
                        'first_name': me.first_name,
                        'last_name': me.last_name,
                    }
                return {'success': True, 'is_valid': False}
            except Exception as e:
                return {'success': False, 'error': str(e), 'is_valid': False}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_check())

    def get_messages(self, session_string, chat_id, limit=50, offset_id=0):
        """Get messages from a specific chat."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _get_messages():
            try:
                await client.connect()
                entity = await client.get_entity(chat_id)
                messages = await client.get_messages(entity, limit=limit, offset_id=offset_id)

                result = []
                for msg in messages:
                    sender_name = ''
                    sender_id = None
                    if msg.sender:
                        sender_id = msg.sender.id
                        if hasattr(msg.sender, 'first_name'):
                            sender_name = msg.sender.first_name or ''
                            if hasattr(msg.sender, 'last_name') and msg.sender.last_name:
                                sender_name += ' ' + msg.sender.last_name
                        elif hasattr(msg.sender, 'title'):
                            sender_name = msg.sender.title

                    result.append({
                        'id': msg.id,
                        'text': msg.text or '',
                        'date': msg.date.isoformat() if msg.date else None,
                        'sender_id': sender_id,
                        'sender_name': sender_name,
                        'is_outgoing': msg.out,
                        'has_media': msg.media is not None,
                        'media_type': type(msg.media).__name__ if msg.media else None,
                        'reply_to_msg_id': msg.reply_to.reply_to_msg_id if msg.reply_to else None,
                        'forwards': msg.forwards,
                        'views': msg.views,
                    })

                return {'success': True, 'messages': result}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_get_messages())

    def get_chat_info(self, session_string, chat_id):
        """Get detailed information about a chat."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _get_chat_info():
            try:
                await client.connect()
                entity = await client.get_entity(chat_id)

                chat_type = 'user'
                members_count = None
                photo = None

                if hasattr(entity, 'megagroup') and entity.megagroup:
                    chat_type = 'supergroup'
                elif hasattr(entity, 'broadcast') and entity.broadcast:
                    chat_type = 'channel'
                elif hasattr(entity, 'participants_count'):
                    chat_type = 'group'

                if hasattr(entity, 'participants_count'):
                    members_count = entity.participants_count

                title = getattr(entity, 'title', None)
                if not title:
                    first_name = getattr(entity, 'first_name', '') or ''
                    last_name = getattr(entity, 'last_name', '') or ''
                    title = f"{first_name} {last_name}".strip()

                return {
                    'success': True,
                    'chat': {
                        'id': entity.id,
                        'title': title,
                        'type': chat_type,
                        'username': getattr(entity, 'username', None),
                        'members_count': members_count,
                        'about': getattr(entity, 'about', None),
                    }
                }
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_get_chat_info())

    def get_all_chats(self, session_string, limit=None):
        """Get all user's chats with full details."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _get_all_chats():
            try:
                await client.connect()
                dialogs = await client.get_dialogs(limit=limit)
                result = []

                for dialog in dialogs:
                    entity = dialog.entity
                    chat_type = 'user'

                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        chat_type = 'supergroup'
                    elif hasattr(entity, 'broadcast') and entity.broadcast:
                        chat_type = 'channel'
                    elif hasattr(entity, 'gigagroup') and entity.gigagroup:
                        chat_type = 'supergroup'
                    elif hasattr(entity, 'participants_count'):
                        chat_type = 'group'

                    last_message = None
                    if dialog.message:
                        last_message = {
                            'id': dialog.message.id,
                            'text': dialog.message.text[:100] if dialog.message.text else '',
                            'date': dialog.message.date.isoformat() if dialog.message.date else None,
                        }

                    result.append({
                        'id': dialog.id,
                        'title': dialog.title or dialog.name,
                        'type': chat_type,
                        'username': getattr(entity, 'username', None),
                        'unread_count': dialog.unread_count,
                        'is_archived': dialog.archived,
                        'is_pinned': dialog.pinned,
                        'last_message': last_message,
                        'members_count': getattr(entity, 'participants_count', None),
                    })

                return {'success': True, 'chats': result, 'total': len(result)}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_get_all_chats())

    def get_all_messages(self, session_string, limit_per_chat=10, max_chats=50):
        """Get recent messages from all chats combined."""
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _get_all_messages():
            try:
                await client.connect()
                dialogs = await client.get_dialogs(limit=max_chats)
                all_messages = []

                for dialog in dialogs:
                    entity = dialog.entity
                    chat_type = 'user'

                    if hasattr(entity, 'megagroup') and entity.megagroup:
                        chat_type = 'supergroup'
                    elif hasattr(entity, 'broadcast') and entity.broadcast:
                        chat_type = 'channel'
                    elif hasattr(entity, 'gigagroup') and entity.gigagroup:
                        chat_type = 'supergroup'
                    elif hasattr(entity, 'participants_count'):
                        chat_type = 'group'

                    chat_title = dialog.title or dialog.name

                    # Get recent messages from this chat
                    messages = await client.get_messages(entity, limit=limit_per_chat)

                    for msg in messages:
                        sender_name = ''
                        sender_id = None
                        if msg.sender:
                            sender_id = msg.sender.id
                            if hasattr(msg.sender, 'first_name'):
                                sender_name = msg.sender.first_name or ''
                                if hasattr(msg.sender, 'last_name') and msg.sender.last_name:
                                    sender_name += ' ' + msg.sender.last_name
                            elif hasattr(msg.sender, 'title'):
                                sender_name = msg.sender.title

                        all_messages.append({
                            'id': msg.id,
                            'chat_id': dialog.id,
                            'chat_title': chat_title,
                            'chat_type': chat_type,
                            'text': msg.text or '',
                            'date': msg.date.isoformat() if msg.date else None,
                            'date_obj': msg.date,
                            'sender_id': sender_id,
                            'sender_name': sender_name,
                            'is_outgoing': msg.out,
                            'has_media': msg.media is not None,
                            'media_type': type(msg.media).__name__ if msg.media else None,
                        })

                # Sort all messages by date (newest first)
                all_messages.sort(key=lambda x: x['date_obj'] or '', reverse=True)

                # Remove date_obj (not JSON serializable)
                for msg in all_messages:
                    del msg['date_obj']

                return {'success': True, 'messages': all_messages, 'total': len(all_messages)}
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_get_all_messages())


# Singleton instance
telegram_manager = TelegramClientManager()
