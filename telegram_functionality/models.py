from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
import base64
import hashlib


class TelegramSession(models.Model):
    """Model to store user's Telegram session data."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_session'
    )
    phone_number = models.CharField(max_length=20)
    session_string = models.TextField(blank=True, null=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True, null=True)
    telegram_first_name = models.CharField(max_length=100, blank=True, null=True)
    telegram_last_name = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Telegram Session'
        verbose_name_plural = 'Telegram Sessions'

    def __str__(self):
        return f"{self.user.email} - {self.phone_number}"

    def _get_encryption_key(self):
        """Generate encryption key from Django secret key."""
        key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        return base64.urlsafe_b64encode(key)

    def set_session_string(self, session_string):
        """Encrypt and store session string."""
        if session_string:
            fernet = Fernet(self._get_encryption_key())
            encrypted = fernet.encrypt(session_string.encode())
            self.session_string = encrypted.decode()

    def get_session_string(self):
        """Decrypt and return session string."""
        if self.session_string:
            fernet = Fernet(self._get_encryption_key())
            decrypted = fernet.decrypt(self.session_string.encode())
            return decrypted.decode()
        return None


class TelegramChat(models.Model):
    """Model to store Telegram chats/dialogs for a user."""

    CHAT_TYPES = [
        ('user', 'User'),
        ('group', 'Group'),
        ('supergroup', 'Supergroup'),
        ('channel', 'Channel'),
    ]

    session = models.ForeignKey(
        TelegramSession,
        on_delete=models.CASCADE,
        related_name='chats'
    )
    chat_id = models.BigIntegerField()
    chat_type = models.CharField(max_length=20, choices=CHAT_TYPES)
    title = models.CharField(max_length=255)
    username = models.CharField(max_length=100, blank=True, null=True)
    members_count = models.IntegerField(null=True, blank=True)
    is_archived = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    last_synced = models.DateTimeField(auto_now=True)
    last_message_id = models.BigIntegerField(null=True, blank=True)
    last_full_sync = models.DateTimeField(null=True, blank=True)
    total_messages = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Telegram Chat'
        verbose_name_plural = 'Telegram Chats'
        unique_together = ['session', 'chat_id']

    def __str__(self):
        return f"{self.title} ({self.chat_type})"


class SyncTask(models.Model):
    """Model to track background sync tasks and their progress."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    TASK_TYPES = [
        ('sync_all', 'Sync All Chats'),
        ('sync_chat', 'Sync Single Chat'),
        ('check_deleted', 'Check Deleted Messages'),
    ]

    session = models.ForeignKey(
        TelegramSession,
        on_delete=models.CASCADE,
        related_name='sync_tasks'
    )
    task_type = models.CharField(max_length=20, choices=TASK_TYPES, default='sync_all')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')

    # Progress tracking
    total_chats = models.IntegerField(default=0)
    synced_chats = models.IntegerField(default=0)
    total_messages = models.IntegerField(default=0)
    synced_messages = models.IntegerField(default=0)
    new_messages = models.IntegerField(default=0)

    # Current activity
    current_chat_id = models.BigIntegerField(null=True, blank=True)
    current_chat_title = models.CharField(max_length=255, blank=True, default='')
    current_chat_progress = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True, default='')

    # Log of activities
    log = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = 'Sync Task'
        verbose_name_plural = 'Sync Tasks'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.status} ({self.created_at})"

    def add_log(self, message):
        """Add a log entry with timestamp."""
        from django.utils import timezone
        timestamp = timezone.now().strftime('%H:%M:%S')
        self.log += f"[{timestamp}] {message}\n"
        self.save(update_fields=['log'])

    @property
    def progress_percent(self):
        """Calculate overall progress percentage."""
        if self.total_chats == 0:
            return 0
        return int((self.synced_chats / self.total_chats) * 100)

    @property
    def is_running(self):
        return self.status == 'running'

    @property
    def is_finished(self):
        return self.status in ['completed', 'failed', 'cancelled']


def telegram_media_path(instance, filename):
    """Generate upload path for telegram media files."""
    # Organize by user_id/chat_id/message_id/filename
    user_id = instance.chat.session.user_id
    chat_id = instance.chat.chat_id
    return f'telegram_media/{user_id}/{chat_id}/{instance.message_id}/{filename}'


class TelegramMessage(models.Model):
    """Model to store Telegram messages with deletion tracking."""

    chat = models.ForeignKey(
        TelegramChat,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    message_id = models.BigIntegerField()
    text = models.TextField(blank=True, default='')
    date = models.DateTimeField()
    sender_id = models.BigIntegerField(null=True, blank=True)
    sender_name = models.CharField(max_length=255, blank=True, default='')
    is_outgoing = models.BooleanField(default=False)
    has_media = models.BooleanField(default=False)
    media_type = models.CharField(max_length=50, blank=True, null=True)
    reply_to_msg_id = models.BigIntegerField(null=True, blank=True)
    forwards = models.IntegerField(null=True, blank=True)
    views = models.IntegerField(null=True, blank=True)

    # Media file storage
    media_file = models.FileField(upload_to=telegram_media_path, blank=True, null=True)
    media_file_name = models.CharField(max_length=255, blank=True, null=True)
    media_file_size = models.BigIntegerField(null=True, blank=True)
    media_mime_type = models.CharField(max_length=100, blank=True, null=True)
    media_width = models.IntegerField(null=True, blank=True)
    media_height = models.IntegerField(null=True, blank=True)
    media_duration = models.IntegerField(null=True, blank=True)  # seconds for audio/video

    # Deletion tracking
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Sync tracking
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Telegram Message'
        verbose_name_plural = 'Telegram Messages'
        unique_together = ['chat', 'message_id']
        ordering = ['-date']

    def __str__(self):
        preview = self.text[:50] + '...' if len(self.text) > 50 else self.text
        status = ' [DELETED]' if self.is_deleted else ''
        return f"{self.chat.title}: {preview}{status}"

    @property
    def is_image(self):
        """Check if media is an image."""
        if self.media_mime_type:
            return self.media_mime_type.startswith('image/')
        return self.media_type in ['MessageMediaPhoto', 'Photo']

    @property
    def is_video(self):
        """Check if media is a video."""
        if self.media_mime_type:
            return self.media_mime_type.startswith('video/')
        return self.media_type in ['MessageMediaDocument'] and self.media_mime_type and 'video' in self.media_mime_type

    @property
    def is_audio(self):
        """Check if media is audio."""
        if self.media_mime_type:
            return self.media_mime_type.startswith('audio/')
        return False

    @property
    def is_document(self):
        """Check if media is a document (not image/video/audio)."""
        if not self.has_media or not self.media_file:
            return False
        return not (self.is_image or self.is_video or self.is_audio)
