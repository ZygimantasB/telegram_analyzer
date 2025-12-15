from django.contrib import admin
from .models import TelegramSession, TelegramChat


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
    list_display = ('title', 'chat_type', 'session', 'username', 'is_archived', 'last_synced')
    list_filter = ('chat_type', 'is_archived', 'last_synced')
    search_fields = ('title', 'username', 'session__user__email')
    readonly_fields = ('chat_id', 'last_synced')
