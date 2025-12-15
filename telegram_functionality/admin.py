from django.contrib import admin
from .models import TelegramSession, TelegramChat, TelegramMessage


@admin.register(TelegramSession)
class TelegramSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number', 'telegram_username', 'is_active', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__email', 'phone_number', 'telegram_username')
    readonly_fields = ('created_at', 'updated_at', 'telegram_user_id')

    fieldsets = (
        (None, {
            'fields': ('user', 'phone_number', 'is_active')
        }),
        ('Telegram Info', {
            'fields': ('telegram_user_id', 'telegram_username', 'telegram_first_name', 'telegram_last_name')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(TelegramChat)
class TelegramChatAdmin(admin.ModelAdmin):
    list_display = ('title', 'chat_type', 'session', 'username', 'is_archived', 'total_messages', 'last_synced')
    list_filter = ('chat_type', 'is_archived', 'is_pinned', 'last_synced')
    search_fields = ('title', 'username', 'session__user__email')
    readonly_fields = ('chat_id', 'last_synced', 'last_full_sync', 'total_messages')


@admin.register(TelegramMessage)
class TelegramMessageAdmin(admin.ModelAdmin):
    list_display = ('message_id', 'chat', 'sender_name', 'text_preview', 'date', 'is_deleted', 'deleted_at')
    list_filter = ('is_deleted', 'is_outgoing', 'has_media', 'chat__chat_type')
    search_fields = ('text', 'sender_name', 'chat__title')
    readonly_fields = ('message_id', 'first_seen_at', 'last_seen_at')
    date_hierarchy = 'date'

    def text_preview(self, obj):
        return obj.text[:50] + '...' if len(obj.text) > 50 else obj.text
    text_preview.short_description = 'Text'

    fieldsets = (
        (None, {
            'fields': ('chat', 'message_id', 'text', 'date')
        }),
        ('Sender Info', {
            'fields': ('sender_id', 'sender_name', 'is_outgoing')
        }),
        ('Media', {
            'fields': ('has_media', 'media_type'),
            'classes': ('collapse',)
        }),
        ('Message Details', {
            'fields': ('reply_to_msg_id', 'forwards', 'views'),
            'classes': ('collapse',)
        }),
        ('Deletion Status', {
            'fields': ('is_deleted', 'deleted_at')
        }),
        ('Sync Info', {
            'fields': ('first_seen_at', 'last_seen_at'),
            'classes': ('collapse',)
        }),
    )
