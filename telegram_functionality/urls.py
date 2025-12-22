from django.urls import path, re_path
from . import views

app_name = 'telegram'

urlpatterns = [
    # Session management (multiple accounts)
    path('sessions/', views.sessions_list, name='sessions'),
    path('sessions/<int:session_id>/switch/', views.switch_session, name='switch_session'),
    path('sessions/<int:session_id>/update/', views.update_session, name='update_session'),
    path('sessions/<int:session_id>/disconnect/', views.telegram_disconnect, name='disconnect_session'),

    # Connection and authentication
    path('connect/', views.telegram_connect, name='connect'),
    path('verify-code/', views.verify_code, name='verify_code'),
    path('verify-2fa/', views.verify_2fa, name='verify_2fa'),
    path('resend-code/', views.resend_code, name='resend_code'),

    # Main views
    path('dashboard/', views.telegram_dashboard, name='dashboard'),
    path('disconnect/', views.telegram_disconnect, name='disconnect'),
    path('sync-chats/', views.sync_chats, name='sync_chats'),

    # Chat views - using re_path to allow negative chat IDs
    path('chats/', views.chat_list, name='chats'),
    path('messages/', views.all_messages, name='all_messages'),
    re_path(r'^chats/(?P<chat_id>-?\d+)/$', views.chat_messages, name='chat_messages'),
    re_path(r'^chats/(?P<chat_id>-?\d+)/load-more/$', views.load_more_messages, name='load_more_messages'),

    # Sync routes
    path('sync-all/', views.sync_all_chats, name='sync_all'),
    re_path(r'^sync/(?P<chat_id>-?\d+)/$', views.sync_chat_messages, name='sync_chat'),

    # Deleted messages
    path('deleted/', views.deleted_messages, name='deleted_messages'),
    path('check-deleted/', views.check_deleted_messages, name='check_deleted'),
    re_path(r'^check-deleted/(?P<chat_id>-?\d+)/$', views.check_deleted_messages, name='check_deleted_chat'),

    # Background sync with progress tracking
    path('start-sync/', views.start_sync, name='start_sync'),
    path('sync-status/<int:task_id>/', views.sync_status, name='sync_status'),
    path('sync-progress/<int:task_id>/', views.sync_progress_api, name='sync_progress'),
    path('cancel-sync/<int:task_id>/', views.cancel_sync, name='cancel_sync'),
    path('sync-history/', views.sync_history, name='sync_history'),

    # Media download
    path('media/<int:message_id>/', views.download_media, name='download_media'),
]
