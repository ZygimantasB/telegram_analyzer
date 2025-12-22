from django.urls import path, re_path
from . import views
from . import views_advanced

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
    path('media/<int:message_id>/trigger-download/', views.trigger_media_download, name='trigger_media_download'),
    path('media/pending/', views.pending_downloads_api, name='pending_downloads_api'),
    path('media/bulk-download/', views.bulk_download_media, name='bulk_download'),
    path('media/start-bulk-download/', views.start_bulk_download, name='start_bulk_download'),

    # Search
    path('search/', views.search_messages, name='search'),
    path('search/chats/', views.search_chats, name='search_chats'),

    # Analytics
    path('analytics/', views_advanced.analytics_dashboard, name='analytics'),
    path('analytics/word-cloud/', views_advanced.analytics_word_cloud, name='analytics_word_cloud'),
    path('analytics/top-senders/', views_advanced.analytics_top_senders, name='analytics_top_senders'),
    path('analytics/heatmap/', views_advanced.analytics_activity_heatmap, name='analytics_heatmap'),
    path('analytics/api/<str:stat_type>/', views_advanced.analytics_api, name='analytics_api'),

    # Export
    path('export/', views_advanced.export_page, name='export'),
    path('export/json/', views_advanced.export_json, name='export_json'),
    path('export/csv/', views_advanced.export_csv, name='export_csv'),
    path('export/html/', views_advanced.export_html, name='export_html'),

    # Bookmarks
    path('bookmarks/', views_advanced.bookmarks_list, name='bookmarks'),
    path('bookmarks/<int:message_id>/toggle/', views_advanced.toggle_bookmark, name='toggle_bookmark'),
    path('bookmarks/<int:bookmark_id>/note/', views_advanced.update_bookmark_note, name='update_bookmark_note'),
    path('bookmarks/<int:bookmark_id>/delete/', views_advanced.delete_bookmark, name='delete_bookmark'),

    # Tags
    path('tags/', views_advanced.tags_list, name='tags'),
    path('tags/create/', views_advanced.create_tag, name='create_tag'),
    path('tags/<int:tag_id>/delete/', views_advanced.delete_tag, name='delete_tag'),
    path('tags/<int:tag_id>/messages/', views_advanced.tagged_messages, name='tagged_messages'),
    path('messages/<int:message_id>/tag/', views_advanced.tag_message, name='tag_message'),

    # Folders
    path('folders/', views_advanced.folders_list, name='folders_list'),
    path('folders/create/', views_advanced.create_folder, name='create_folder'),
    path('folders/<int:folder_id>/delete/', views_advanced.delete_folder, name='delete_folder'),
    path('folders/<int:folder_id>/chats/', views_advanced.folder_chats_view, name='folder_chats'),
    path('folders/<int:folder_id>/add-chat/', views_advanced.folder_add_chats, name='folder_add_chat'),
    path('folders/<int:folder_id>/remove-chat/', views_advanced.folder_remove_chat, name='folder_remove_chat'),

    # Notes
    path('notes/', views_advanced.notes_list, name='notes'),
    path('notes/<int:message_id>/add/', views_advanced.add_note, name='add_note'),
    path('notes/<int:note_id>/delete/', views_advanced.delete_note, name='delete_note'),

    # Media Gallery
    path('gallery/', views_advanced.media_gallery, name='media_gallery'),
    path('gallery/slideshow/', views_advanced.media_slideshow, name='media_slideshow'),
    path('gallery/duplicates/', views_advanced.find_duplicates, name='find_duplicates'),
    path('gallery/compute-hashes/', views_advanced.compute_media_hashes, name='compute_media_hashes'),

    # Keyword Alerts
    path('alerts/', views_advanced.keyword_alerts_list, name='keyword_alerts'),
    path('alerts/create/', views_advanced.create_keyword_alert, name='create_keyword_alert'),
    path('alerts/<int:alert_id>/toggle/', views_advanced.toggle_keyword_alert, name='toggle_keyword_alert'),
    path('alerts/<int:alert_id>/delete/', views_advanced.delete_keyword_alert, name='delete_keyword_alert'),
    path('alerts/<int:alert_id>/triggers/', views_advanced.alert_triggers_list, name='alert_triggers'),
    path('alerts/triggers/', views_advanced.all_triggers_list, name='all_triggers'),
    path('alerts/triggers/<int:trigger_id>/read/', views_advanced.mark_trigger_read, name='mark_trigger_read'),
    path('alerts/triggers/clear/', views_advanced.clear_all_triggers, name='clear_triggers'),
    path('alerts/deletion-config/', views_advanced.deletion_alert_config_view, name='deletion_alert_config'),

    # Scheduled Backups
    path('backups/', views_advanced.scheduled_backups_list, name='scheduled_backups'),
    path('backups/create/', views_advanced.create_scheduled_backup, name='create_backup_schedule'),
    path('backups/<int:backup_id>/toggle/', views_advanced.toggle_scheduled_backup, name='toggle_scheduled_backup'),
    path('backups/<int:backup_id>/delete/', views_advanced.delete_scheduled_backup, name='delete_scheduled_backup'),
    path('backups/<int:backup_id>/run/', views_advanced.run_backup_now, name='run_backup_now'),
    path('backups/download/<int:history_id>/', views_advanced.download_backup, name='download_backup'),

    # Tags additional
    path('tags/tagging/<int:tagging_id>/remove/', views_advanced.remove_tagging, name='remove_tagging'),
    path('tags/list/', views_advanced.tags_list, name='tags_list'),

    # Audit Log
    path('audit-log/', views_advanced.audit_log_list, name='audit_log'),

    # Members / Participants
    path('members/', views_advanced.members_list, name='members_list'),
    path('members/analytics/', views_advanced.members_analytics, name='members_analytics'),
    path('members/export/', views_advanced.export_members, name='export_members'),
    re_path(r'^members/chat/(?P<chat_id>-?\d+)/$', views_advanced.chat_members, name='chat_members'),
    re_path(r'^members/chat/(?P<chat_id>-?\d+)/sync/$', views_advanced.sync_chat_members, name='sync_chat_members'),
    re_path(r'^members/chat/(?P<chat_id>-?\d+)/export/$', views_advanced.export_members, name='export_chat_members'),
    path('members/user/<int:user_id>/', views_advanced.user_detail, name='user_detail'),
]
