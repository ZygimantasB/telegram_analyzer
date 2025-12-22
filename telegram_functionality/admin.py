from django.contrib import admin
from .models import TelegramSession, TelegramChat, TelegramMessage, SyncTask


@admin.register(TelegramSession)
class TelegramSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone_number', 'display_name', 'telegram_username', 'is_active', 'is_current', 'created_at')
    list_filter = ('is_active', 'is_current', 'created_at')
    search_fields = ('user__email', 'phone_number', 'telegram_username', 'display_name')
    readonly_fields = ('created_at', 'updated_at', 'telegram_user_id')
    list_editable = ('is_current',)

    fieldsets = (
        (None, {
            'fields': ('user', 'phone_number', 'display_name', 'is_active', 'is_current')
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


@admin.register(SyncTask)
class SyncTaskAdmin(admin.ModelAdmin):
    list_display = ('id', 'session', 'task_type', 'status', 'progress_display', 'created_at', 'completed_at')
    list_filter = ('status', 'task_type', 'created_at')
    search_fields = ('session__user__email',)
    readonly_fields = ('created_at', 'started_at', 'completed_at', 'log')
    ordering = ('-created_at',)

    def progress_display(self, obj):
        return f"{obj.synced_chats}/{obj.total_chats} chats, {obj.synced_messages} msgs"
    progress_display.short_description = 'Progress'

    fieldsets = (
        (None, {
            'fields': ('session', 'task_type', 'status')
        }),
        ('Progress', {
            'fields': ('total_chats', 'synced_chats', 'total_messages', 'synced_messages', 'new_messages')
        }),
        ('Current Activity', {
            'fields': ('current_chat_id', 'current_chat_title', 'current_chat_progress')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'started_at', 'completed_at')
        }),
        ('Error', {
            'fields': ('error_message',),
            'classes': ('collapse',)
        }),
        ('Log', {
            'fields': ('log',),
            'classes': ('collapse',)
        }),
    )
