import asyncio
import logging
import os
import mimetypes
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
    FloodWaitError,
)
from telethon.tl.types import (
    MessageMediaPhoto,
    MessageMediaDocument,
    MessageMediaWebPage,
    DocumentAttributeFilename,
    DocumentAttributeVideo,
    DocumentAttributeAudio,
    DocumentAttributeImageSize,
)
from django.conf import settings

# Configure logger for this module
logger = logging.getLogger('telegram_functionality.services')
sync_logger = logging.getLogger('telegram_functionality.sync')


class TelegramClientManager:
    """Manager class for handling Telethon client operations."""

    def __init__(self):
        self.api_id = settings.TELEGRAM_API_ID
        self.api_hash = settings.TELEGRAM_API_HASH
        self._clients = {}
        logger.debug("TelegramClientManager initialized")

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

    def _get_media_info(self, message):
        """Extract media information from a Telegram message.

        Returns dict with media metadata or None if no media.
        """
        if not message.media:
            return None

        media = message.media
        media_info = {
            'type': type(media).__name__,
            'mime_type': None,
            'file_name': None,
            'file_size': None,
            'width': None,
            'height': None,
            'duration': None,
        }

        if isinstance(media, MessageMediaPhoto):
            media_info['mime_type'] = 'image/jpeg'
            media_info['file_name'] = f'photo_{message.id}.jpg'
            if media.photo:
                # Get largest photo size
                if hasattr(media.photo, 'sizes') and media.photo.sizes:
                    largest = max(media.photo.sizes, key=lambda s: getattr(s, 'size', 0) if hasattr(s, 'size') else 0)
                    if hasattr(largest, 'w'):
                        media_info['width'] = largest.w
                    if hasattr(largest, 'h'):
                        media_info['height'] = largest.h
                    if hasattr(largest, 'size'):
                        media_info['file_size'] = largest.size

        elif isinstance(media, MessageMediaDocument):
            doc = media.document
            if doc:
                media_info['mime_type'] = doc.mime_type
                media_info['file_size'] = doc.size

                # Get filename and other attributes
                for attr in doc.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        media_info['file_name'] = attr.file_name
                    elif isinstance(attr, DocumentAttributeVideo):
                        media_info['width'] = attr.w
                        media_info['height'] = attr.h
                        media_info['duration'] = attr.duration
                    elif isinstance(attr, DocumentAttributeAudio):
                        media_info['duration'] = attr.duration
                    elif isinstance(attr, DocumentAttributeImageSize):
                        media_info['width'] = attr.w
                        media_info['height'] = attr.h

                # Generate filename if not found
                if not media_info['file_name']:
                    ext = mimetypes.guess_extension(doc.mime_type or '') or ''
                    media_info['file_name'] = f'document_{message.id}{ext}'

        elif isinstance(media, MessageMediaWebPage):
            # Web pages don't have downloadable media
            return None

        return media_info

    async def _download_media_async(self, client, message, save_dir, user_id, chat_id):
        """Download media from a message asynchronously.

        Args:
            client: Connected Telethon client
            message: Telegram message object
            save_dir: Base directory for media storage
            user_id: User ID for path organization
            chat_id: Chat ID for path organization

        Returns:
            Dict with file path and media info, or None if no media/failed
        """
        if not message.media:
            return None

        media_info = self._get_media_info(message)
        if not media_info:
            return None

        try:
            # Create directory structure: media/telegram_media/user_id/chat_id/message_id/
            media_dir = Path(save_dir) / 'telegram_media' / str(user_id) / str(chat_id) / str(message.id)
            media_dir.mkdir(parents=True, exist_ok=True)

            file_name = media_info['file_name'] or f'media_{message.id}'
            file_path = media_dir / file_name

            # Download the media
            downloaded_path = await client.download_media(message, file=str(file_path))

            if downloaded_path:
                # Get actual file size if not known
                if not media_info['file_size']:
                    media_info['file_size'] = os.path.getsize(downloaded_path)

                # Return relative path from MEDIA_ROOT
                rel_path = Path(downloaded_path).relative_to(save_dir)
                return {
                    'file_path': str(rel_path),
                    'file_name': media_info['file_name'],
                    'file_size': media_info['file_size'],
                    'mime_type': media_info['mime_type'],
                    'width': media_info['width'],
                    'height': media_info['height'],
                    'duration': media_info['duration'],
                }
        except Exception as e:
            logger.warning(f"Failed to download media for message {message.id}: {e}")

        return None

    async def _send_code_async(self, client, phone_number):
        """Send verification code to phone number."""
        await client.connect()
        result = await client.send_code_request(phone_number)
        return result

    def send_code(self, phone_number):
        """Synchronous wrapper to send verification code."""
        logger.info(f"API CALL: send_code - phone: {phone_number[:4]}****")
        loop = self._get_event_loop()
        client = self.get_client()

        async def _send():
            try:
                logger.debug("Connecting to Telegram...")
                await client.connect()
                logger.debug("Sending code request...")
                result = await client.send_code_request(phone_number)
                session_string = client.session.save()
                logger.info(f"Code sent successfully to {phone_number[:4]}****")
                return {
                    'success': True,
                    'phone_code_hash': result.phone_code_hash,
                    'session_string': session_string,
                }
            except FloodWaitError as e:
                logger.warning(f"FloodWaitError: Need to wait {e.seconds} seconds")
                return {
                    'success': False,
                    'error': f'Too many attempts. Please wait {e.seconds} seconds.',
                    'flood_wait': e.seconds,
                }
            except Exception as e:
                logger.error(f"Error sending code: {type(e).__name__}: {str(e)}")
                return {
                    'success': False,
                    'error': str(e),
                }
            finally:
                await client.disconnect()
                logger.debug("Disconnected from Telegram")

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

    def fetch_all_messages_from_chat(self, session_string, chat_id, min_id=0,
                                       download_media=False, user_id=None, media_dir=None):
        """Fetch ALL messages from a chat for database storage.

        Args:
            session_string: Telegram session string
            chat_id: Chat ID to fetch messages from
            min_id: Only fetch messages with ID > min_id (for incremental sync)
            download_media: Whether to download media files
            user_id: User ID for organizing media files (required if download_media=True)
            media_dir: Base directory for media storage (required if download_media=True)

        Returns:
            Dict with success, messages list, and total count
        """
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _fetch_all():
            try:
                await client.connect()
                entity = await client.get_entity(chat_id)
                all_messages = []
                offset_id = 0
                batch_size = 100

                while True:
                    messages = await client.get_messages(
                        entity,
                        limit=batch_size,
                        offset_id=offset_id,
                        min_id=min_id
                    )

                    if not messages:
                        break

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

                        msg_data = {
                            'id': msg.id,
                            'text': msg.text or '',
                            'date': msg.date,
                            'sender_id': sender_id,
                            'sender_name': sender_name,
                            'is_outgoing': msg.out,
                            'has_media': msg.media is not None,
                            'media_type': type(msg.media).__name__ if msg.media else None,
                            'reply_to_msg_id': msg.reply_to.reply_to_msg_id if msg.reply_to else None,
                            'forwards': msg.forwards,
                            'views': msg.views,
                            # Media fields (will be populated if download_media=True)
                            'media_file_path': None,
                            'media_file_name': None,
                            'media_file_size': None,
                            'media_mime_type': None,
                            'media_width': None,
                            'media_height': None,
                            'media_duration': None,
                        }

                        # Download media if requested
                        if download_media and msg.media and user_id and media_dir:
                            media_result = await self._download_media_async(
                                client, msg, media_dir, user_id, chat_id
                            )
                            if media_result:
                                msg_data['media_file_path'] = media_result['file_path']
                                msg_data['media_file_name'] = media_result['file_name']
                                msg_data['media_file_size'] = media_result['file_size']
                                msg_data['media_mime_type'] = media_result['mime_type']
                                msg_data['media_width'] = media_result['width']
                                msg_data['media_height'] = media_result['height']
                                msg_data['media_duration'] = media_result['duration']

                        all_messages.append(msg_data)

                    offset_id = messages[-1].id

                    # Safety check to prevent infinite loops
                    if len(messages) < batch_size:
                        break

                return {
                    'success': True,
                    'messages': all_messages,
                    'total': len(all_messages)
                }
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_fetch_all())

    def get_message_ids_from_chat(self, session_string, chat_id, limit=None):
        """Get all message IDs from a chat (for deletion checking).

        Returns only message IDs to compare against database.
        """
        loop = self._get_event_loop()
        client = self.get_client(session_string)

        async def _get_ids():
            try:
                await client.connect()
                entity = await client.get_entity(chat_id)
                message_ids = set()
                offset_id = 0
                batch_size = 100
                fetched = 0

                while True:
                    messages = await client.get_messages(
                        entity,
                        limit=batch_size,
                        offset_id=offset_id
                    )

                    if not messages:
                        break

                    for msg in messages:
                        message_ids.add(msg.id)

                    offset_id = messages[-1].id
                    fetched += len(messages)

                    if limit and fetched >= limit:
                        break

                    if len(messages) < batch_size:
                        break

                return {
                    'success': True,
                    'message_ids': message_ids,
                    'total': len(message_ids)
                }
            except Exception as e:
                return {'success': False, 'error': str(e)}
            finally:
                await client.disconnect()

        return loop.run_until_complete(_get_ids())


def run_background_sync(sync_task_id):
        """Run sync in background thread with progress updates.

        This function is designed to be called from a separate thread.
        It updates the SyncTask model with progress as it goes.
        """
        import threading
        from django.utils import timezone
        from django.conf import settings as django_settings
        from django.core.files import File
        from .models import SyncTask, TelegramChat, TelegramMessage

        sync_logger.info(f"BACKGROUND SYNC STARTED: Task #{sync_task_id}")

        # Get media directory from Django settings
        media_dir = str(django_settings.MEDIA_ROOT)

        try:
            sync_task = SyncTask.objects.get(id=sync_task_id)
            session = sync_task.session
            session_string = session.get_session_string()
            sync_logger.info(f"Task #{sync_task_id}: Retrieved session for user {session.user_id}")

            # Update status to running
            sync_task.status = 'running'
            sync_task.started_at = timezone.now()
            sync_task.save()
            sync_task.add_log('Sync started')

            manager = TelegramClientManager()

            # First, get all chats
            sync_task.add_log('Fetching chat list from Telegram...')
            chats_result = manager.get_all_chats(session_string)

            if not chats_result['success']:
                error_msg = chats_result.get('error', 'Failed to fetch chats')
                sync_logger.error(f"Task #{sync_task_id}: Failed to fetch chats - {error_msg}")
                sync_task.status = 'failed'
                sync_task.error_message = error_msg
                sync_task.completed_at = timezone.now()
                sync_task.save()
                return

            chats = chats_result['chats']
            sync_task.total_chats = len(chats)
            sync_task.save()
            sync_task.add_log(f'Found {len(chats)} chats')
            sync_logger.info(f"Task #{sync_task_id}: Found {len(chats)} chats to sync")

            # Sync each chat
            for i, chat_data in enumerate(chats):
                # Check if task was cancelled
                sync_task.refresh_from_db()
                if sync_task.status == 'cancelled':
                    sync_logger.info(f"Task #{sync_task_id}: Cancelled by user at chat {i+1}/{len(chats)}")
                    sync_task.add_log('Sync cancelled by user')
                    sync_task.completed_at = timezone.now()
                    sync_task.save()
                    return

                chat_id = chat_data['id']
                chat_title = chat_data['title']
                sync_logger.debug(f"Task #{sync_task_id}: Processing chat {i+1}/{len(chats)}: {chat_title}")

                # Update current chat info
                sync_task.current_chat_id = chat_id
                sync_task.current_chat_title = chat_title
                sync_task.current_chat_progress = 0
                sync_task.save()
                sync_task.add_log(f'Syncing chat: {chat_title}')

                # Get or create TelegramChat
                telegram_chat, created = TelegramChat.objects.get_or_create(
                    session=session,
                    chat_id=chat_id,
                    defaults={
                        'chat_type': chat_data['type'],
                        'title': chat_title,
                        'username': chat_data.get('username'),
                        'members_count': chat_data.get('members_count'),
                        'is_archived': chat_data.get('is_archived', False),
                        'is_pinned': chat_data.get('is_pinned', False),
                    }
                )

                if not created:
                    # Update existing chat info
                    telegram_chat.title = chat_title
                    telegram_chat.chat_type = chat_data['type']
                    telegram_chat.username = chat_data.get('username')
                    telegram_chat.members_count = chat_data.get('members_count')
                    telegram_chat.is_archived = chat_data.get('is_archived', False)
                    telegram_chat.is_pinned = chat_data.get('is_pinned', False)
                    telegram_chat.save()

                # Fetch messages for this chat (with media download)
                min_id = telegram_chat.last_message_id or 0
                messages_result = manager.fetch_all_messages_from_chat(
                    session_string,
                    chat_id,
                    min_id=min_id,
                    download_media=True,
                    user_id=session.user_id,
                    media_dir=media_dir
                )

                if messages_result['success']:
                    messages = messages_result['messages']
                    new_count = 0
                    media_count = 0

                    for msg_data in messages:
                        msg_obj, msg_created = TelegramMessage.objects.get_or_create(
                            chat=telegram_chat,
                            message_id=msg_data['id'],
                            defaults={
                                'text': msg_data['text'],
                                'date': msg_data['date'],
                                'sender_id': msg_data['sender_id'],
                                'sender_name': msg_data['sender_name'],
                                'is_outgoing': msg_data['is_outgoing'],
                                'has_media': msg_data['has_media'],
                                'media_type': msg_data['media_type'],
                                'reply_to_msg_id': msg_data['reply_to_msg_id'],
                                'forwards': msg_data['forwards'],
                                'views': msg_data['views'],
                                # Media file fields
                                'media_file': msg_data.get('media_file_path'),
                                'media_file_name': msg_data.get('media_file_name'),
                                'media_file_size': msg_data.get('media_file_size'),
                                'media_mime_type': msg_data.get('media_mime_type'),
                                'media_width': msg_data.get('media_width'),
                                'media_height': msg_data.get('media_height'),
                                'media_duration': msg_data.get('media_duration'),
                            }
                        )
                        if msg_created:
                            new_count += 1
                            if msg_data.get('media_file_path'):
                                media_count += 1
                        elif msg_data.get('media_file_path') and not msg_obj.media_file:
                            # Update existing message with media if it wasn't downloaded before
                            msg_obj.media_file = msg_data['media_file_path']
                            msg_obj.media_file_name = msg_data.get('media_file_name')
                            msg_obj.media_file_size = msg_data.get('media_file_size')
                            msg_obj.media_mime_type = msg_data.get('media_mime_type')
                            msg_obj.media_width = msg_data.get('media_width')
                            msg_obj.media_height = msg_data.get('media_height')
                            msg_obj.media_duration = msg_data.get('media_duration')
                            msg_obj.save()
                            media_count += 1

                    # Update chat stats
                    if messages:
                        max_msg_id = max(m['id'] for m in messages)
                        telegram_chat.last_message_id = max_msg_id
                    telegram_chat.total_messages = telegram_chat.messages.count()
                    telegram_chat.last_full_sync = timezone.now()
                    telegram_chat.save()

                    # Update sync task progress
                    sync_task.synced_messages += len(messages)
                    sync_task.new_messages += new_count
                    sync_task.total_messages += len(messages)
                    media_info = f", {media_count} media files" if media_count > 0 else ""
                    sync_task.add_log(f'  - Fetched {len(messages)} messages ({new_count} new{media_info})')
                    sync_logger.debug(f"Task #{sync_task_id}: Chat '{chat_title}' - {len(messages)} messages ({new_count} new, {media_count} media)")
                else:
                    error_msg = messages_result.get("error", "Unknown error")
                    sync_logger.warning(f"Task #{sync_task_id}: Error syncing chat '{chat_title}': {error_msg}")
                    sync_task.add_log(f'  - Error: {error_msg}')

                # Update synced chats count
                sync_task.synced_chats = i + 1
                sync_task.save()

            # Complete
            sync_task.status = 'completed'
            sync_task.completed_at = timezone.now()
            sync_task.current_chat_id = None
            sync_task.current_chat_title = ''
            sync_task.save()
            sync_task.add_log(f'Sync completed! {sync_task.synced_messages} messages from {sync_task.synced_chats} chats')
            sync_logger.info(f"BACKGROUND SYNC COMPLETED: Task #{sync_task_id} - {sync_task.synced_messages} messages from {sync_task.synced_chats} chats ({sync_task.new_messages} new)")

        except Exception as e:
            sync_logger.error(f"BACKGROUND SYNC FAILED: Task #{sync_task_id} - {type(e).__name__}: {str(e)}")
            try:
                sync_task = SyncTask.objects.get(id=sync_task_id)
                sync_task.status = 'failed'
                sync_task.error_message = str(e)
                sync_task.completed_at = timezone.now()
                sync_task.save()
                sync_task.add_log(f'Error: {str(e)}')
            except Exception as db_error:
                sync_logger.error(f"Failed to update SyncTask #{sync_task_id}: {str(db_error)}")


def start_background_sync(sync_task):
    """Start the sync in a background thread."""
    import threading
    sync_logger.info(f"Starting background thread for SyncTask #{sync_task.id}")
    thread = threading.Thread(
        target=run_background_sync,
        args=(sync_task.id,),
        daemon=True,
        name=f"sync_task_{sync_task.id}"
    )
    thread.start()
    sync_logger.debug(f"Background thread started: {thread.name}")
    return thread


# Singleton instance
telegram_manager = TelegramClientManager()
