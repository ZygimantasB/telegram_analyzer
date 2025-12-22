from django.db import models
from django.conf import settings
from cryptography.fernet import Fernet
import base64
import hashlib


class TelegramSession(models.Model):
    """Model to store user's Telegram session data. Supports multiple sessions per user."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='telegram_sessions'
    )
    phone_number = models.CharField(max_length=20)
    session_string = models.TextField(blank=True, null=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=100, blank=True, null=True)
    telegram_first_name = models.CharField(max_length=100, blank=True, null=True)
    telegram_last_name = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=False)
    is_current = models.BooleanField(default=False)  # Which session is currently selected
    display_name = models.CharField(max_length=100, blank=True, null=True)  # Custom name for the session
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Telegram Session'
        verbose_name_plural = 'Telegram Sessions'
        unique_together = ['user', 'phone_number']  # One phone number per user

    def __str__(self):
        name = self.display_name or self.telegram_username or self.phone_number
        return f"{self.user.email} - {name}"

    def get_display_name(self):
        """Get a user-friendly display name for the session."""
        if self.display_name:
            return self.display_name
        if self.telegram_first_name:
            name = self.telegram_first_name
            if self.telegram_last_name:
                name += f" {self.telegram_last_name}"
            return name
        if self.telegram_username:
            return f"@{self.telegram_username}"
        return self.phone_number

    def set_as_current(self):
        """Set this session as the current active session for the user."""
        # Unset current from all other sessions for this user
        TelegramSession.objects.filter(user=self.user, is_current=True).update(is_current=False)
        self.is_current = True
        self.save(update_fields=['is_current'])

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


# ============================================
# Organization Features
# ============================================

class ChatFolder(models.Model):
    """Custom folders for organizing chats."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_folders'
    )
    name = models.CharField(max_length=100)
    color = models.CharField(max_length=7, default='#0088cc')  # Hex color
    icon = models.CharField(max_length=50, default='bi-folder')  # Bootstrap icon
    order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Chat Folder'
        verbose_name_plural = 'Chat Folders'
        ordering = ['order', 'name']
        unique_together = ['user', 'name']

    def __str__(self):
        return f"{self.user.email} - {self.name}"


class ChatFolderMembership(models.Model):
    """Many-to-many relationship between chats and folders."""

    folder = models.ForeignKey(
        ChatFolder,
        on_delete=models.CASCADE,
        related_name='memberships'
    )
    chat = models.ForeignKey(
        TelegramChat,
        on_delete=models.CASCADE,
        related_name='folder_memberships'
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['folder', 'chat']


class Tag(models.Model):
    """Custom tags for labeling messages."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_tags'
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default='#6c757d')  # Hex color
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
        unique_together = ['user', 'name']
        ordering = ['name']

    def __str__(self):
        return self.name


class MessageBookmark(models.Model):
    """Bookmarked/saved messages."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='bookmarks'
    )
    message = models.ForeignKey(
        TelegramMessage,
        on_delete=models.CASCADE,
        related_name='bookmarks'
    )
    note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Bookmark'
        verbose_name_plural = 'Bookmarks'
        unique_together = ['user', 'message']
        ordering = ['-created_at']

    def __str__(self):
        return f"Bookmark: {self.message}"


class MessageTagging(models.Model):
    """Many-to-many relationship between messages and tags."""

    tag = models.ForeignKey(
        Tag,
        on_delete=models.CASCADE,
        related_name='message_taggings'
    )
    message = models.ForeignKey(
        TelegramMessage,
        on_delete=models.CASCADE,
        related_name='taggings'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['tag', 'message']


class MessageNote(models.Model):
    """Personal notes attached to messages."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='message_notes'
    )
    message = models.ForeignKey(
        TelegramMessage,
        on_delete=models.CASCADE,
        related_name='notes'
    )
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Message Note'
        verbose_name_plural = 'Message Notes'
        ordering = ['-created_at']

    def __str__(self):
        return f"Note on {self.message}"


# ============================================
# Message Edit Tracking
# ============================================

class MessageEdit(models.Model):
    """Track message edit history."""

    message = models.ForeignKey(
        TelegramMessage,
        on_delete=models.CASCADE,
        related_name='edits'
    )
    previous_text = models.TextField()
    new_text = models.TextField()
    edited_at = models.DateTimeField()
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Message Edit'
        verbose_name_plural = 'Message Edits'
        ordering = ['-edited_at']

    def __str__(self):
        return f"Edit on message {self.message.message_id}"


# ============================================
# Alerts & Notifications
# ============================================

class KeywordAlert(models.Model):
    """Keyword monitoring alerts."""

    MATCH_TYPES = [
        ('exact', 'Exact Match'),
        ('contains', 'Contains'),
        ('regex', 'Regular Expression'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='keyword_alerts'
    )
    keyword = models.CharField(max_length=200)
    match_type = models.CharField(max_length=20, choices=MATCH_TYPES, default='contains')
    is_active = models.BooleanField(default=True)
    case_sensitive = models.BooleanField(default=False)

    # Optional filters
    chats = models.ManyToManyField(TelegramChat, blank=True, related_name='keyword_alerts')

    # Notification settings
    notify_email = models.BooleanField(default=False)
    notify_webhook = models.BooleanField(default=False)
    webhook_url = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    last_triggered = models.DateTimeField(null=True, blank=True)
    trigger_count = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Keyword Alert'
        verbose_name_plural = 'Keyword Alerts'
        ordering = ['-created_at']

    def __str__(self):
        return f"Alert: {self.keyword}"


class AlertTrigger(models.Model):
    """Log of triggered alerts."""

    alert = models.ForeignKey(
        KeywordAlert,
        on_delete=models.CASCADE,
        related_name='triggers'
    )
    message = models.ForeignKey(
        TelegramMessage,
        on_delete=models.CASCADE,
        related_name='alert_triggers'
    )
    triggered_at = models.DateTimeField(auto_now_add=True)
    notified = models.BooleanField(default=False)

    class Meta:
        ordering = ['-triggered_at']


class DeletionAlertConfig(models.Model):
    """Configuration for deletion alerts."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deletion_alert_config'
    )
    is_enabled = models.BooleanField(default=False)
    notify_email = models.BooleanField(default=False)
    notify_webhook = models.BooleanField(default=False)
    webhook_url = models.URLField(blank=True, null=True)

    # Filter options
    only_own_messages = models.BooleanField(default=False)
    min_message_age_hours = models.IntegerField(default=0)  # Only alert if message was older than X hours

    class Meta:
        verbose_name = 'Deletion Alert Config'
        verbose_name_plural = 'Deletion Alert Configs'


# ============================================
# Scheduled Backups
# ============================================

class ScheduledBackup(models.Model):
    """Configuration for scheduled automatic backups."""

    FREQUENCY_CHOICES = [
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ]

    EXPORT_FORMATS = [
        ('json', 'JSON'),
        ('csv', 'CSV'),
        ('html', 'HTML'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='scheduled_backups'
    )
    session = models.ForeignKey(
        TelegramSession,
        on_delete=models.CASCADE,
        related_name='scheduled_backups'
    )
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    frequency = models.CharField(max_length=20, choices=FREQUENCY_CHOICES, default='weekly')
    export_format = models.CharField(max_length=10, choices=EXPORT_FORMATS, default='json')
    include_media = models.BooleanField(default=False)

    # Schedule
    last_run = models.DateTimeField(null=True, blank=True)
    next_run = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Scheduled Backup'
        verbose_name_plural = 'Scheduled Backups'

    def __str__(self):
        return f"{self.name} ({self.frequency})"


class BackupHistory(models.Model):
    """History of completed backups."""

    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    scheduled_backup = models.ForeignKey(
        ScheduledBackup,
        on_delete=models.CASCADE,
        related_name='history',
        null=True, blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='backup_history'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    file_path = models.CharField(max_length=500, blank=True)
    file_size = models.BigIntegerField(default=0)
    messages_count = models.IntegerField(default=0)
    chats_count = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Backup History'
        verbose_name_plural = 'Backup History'
        ordering = ['-created_at']


# ============================================
# Audit Log
# ============================================

class AuditLog(models.Model):
    """Audit log for tracking user actions."""

    ACTION_TYPES = [
        ('login', 'Login'),
        ('logout', 'Logout'),
        ('connect_telegram', 'Connect Telegram'),
        ('disconnect_telegram', 'Disconnect Telegram'),
        ('sync_chats', 'Sync Chats'),
        ('sync_messages', 'Sync Messages'),
        ('export_data', 'Export Data'),
        ('delete_data', 'Delete Data'),
        ('create_bookmark', 'Create Bookmark'),
        ('delete_bookmark', 'Delete Bookmark'),
        ('create_tag', 'Create Tag'),
        ('create_folder', 'Create Folder'),
        ('download_media', 'Download Media'),
        ('view_message', 'View Message'),
        ('search', 'Search'),
        ('settings_change', 'Settings Change'),
        ('other', 'Other'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='audit_logs'
    )
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    description = models.TextField(blank=True, default='')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')

    # Optional references
    session = models.ForeignKey(
        TelegramSession,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_logs'
    )
    chat = models.ForeignKey(
        TelegramChat,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_logs'
    )
    message = models.ForeignKey(
        TelegramMessage,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='audit_logs'
    )

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.action} at {self.created_at}"


# ============================================
# Media & Duplicate Detection
# ============================================

class MediaHash(models.Model):
    """Store perceptual hashes for media files to detect duplicates."""

    message = models.OneToOneField(
        TelegramMessage,
        on_delete=models.CASCADE,
        related_name='media_hash'
    )

    # Different hash types for comparison
    file_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)  # MD5/SHA256
    perceptual_hash = models.CharField(max_length=64, blank=True, null=True, db_index=True)  # pHash for images

    file_size = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Media Hash'
        verbose_name_plural = 'Media Hashes'
        indexes = [
            models.Index(fields=['file_hash']),
            models.Index(fields=['perceptual_hash']),
        ]


# ============================================
# Analytics Cache
# ============================================

class AnalyticsCache(models.Model):
    """Cache for computed analytics to improve performance."""

    CACHE_TYPES = [
        ('daily_stats', 'Daily Statistics'),
        ('hourly_activity', 'Hourly Activity'),
        ('top_senders', 'Top Senders'),
        ('word_frequency', 'Word Frequency'),
        ('media_stats', 'Media Statistics'),
    ]

    session = models.ForeignKey(
        TelegramSession,
        on_delete=models.CASCADE,
        related_name='analytics_cache'
    )
    cache_type = models.CharField(max_length=50, choices=CACHE_TYPES)
    data = models.JSONField(default=dict)

    # Time range this cache covers
    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        verbose_name = 'Analytics Cache'
        verbose_name_plural = 'Analytics Caches'
        unique_together = ['session', 'cache_type', 'date_from', 'date_to']
