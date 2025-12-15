from django.urls import path, re_path
from . import views

app_name = 'telegram'

urlpatterns = [
    path('connect/', views.telegram_connect, name='connect'),
    path('verify-code/', views.verify_code, name='verify_code'),
    path('verify-2fa/', views.verify_2fa, name='verify_2fa'),
    path('dashboard/', views.telegram_dashboard, name='dashboard'),
    path('disconnect/', views.telegram_disconnect, name='disconnect'),
    path('sync-chats/', views.sync_chats, name='sync_chats'),
    path('resend-code/', views.resend_code, name='resend_code'),
    # Chat views - using re_path to allow negative chat IDs
    path('chats/', views.chat_list, name='chats'),
    re_path(r'^chats/(?P<chat_id>-?\d+)/$', views.chat_messages, name='chat_messages'),
    re_path(r'^chats/(?P<chat_id>-?\d+)/load-more/$', views.load_more_messages, name='load_more_messages'),
]
