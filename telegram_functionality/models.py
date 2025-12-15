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
    last_synced = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Telegram Chat'
        verbose_name_plural = 'Telegram Chats'
        unique_together = ['session', 'chat_id']

    def __str__(self):
        return f"{self.title} ({self.chat_type})"
