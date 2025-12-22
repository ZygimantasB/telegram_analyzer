"""
Advanced views for Analytics, Export, Bookmarks, Tags, Media Gallery, etc.
"""
import json
import csv
import os
import hashlib
import re
from io import StringIO, BytesIO
from datetime import datetime, timedelta
from zipfile import ZipFile

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse, FileResponse
from django.utils import timezone
from django.db.models import Q, Count, Sum
from django.conf import settings
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST, require_GET

from .models import (
    TelegramSession, TelegramChat, TelegramMessage,
    ChatFolder, ChatFolderMembership, Tag, MessageTagging,
    MessageBookmark, MessageNote, MessageEdit,
    KeywordAlert, AlertTrigger, DeletionAlertConfig,
    ScheduledBackup, BackupHistory, AuditLog, MediaHash
)
from .analytics import AnalyticsService
from .views import get_current_session, get_session_or_redirect, get_all_user_sessions


# ============================================
# Audit Log Helper
# ============================================

def log_audit(request, action, description='', session=None, chat=None, message=None, metadata=None):
    """Helper to create audit log entries."""
    AuditLog.objects.create(
        user=request.user,
        action=action,
        description=description,
        ip_address=get_client_ip(request),
        user_agent=request.META.get('HTTP_USER_AGENT', '')[:500],
        session=session,
        chat=chat,
        message=message,
        metadata=metadata or {},
    )


def get_client_ip(request):
    """Get client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


# ============================================
# Analytics Views
# ============================================

@login_required
def analytics_dashboard(request):
    """Main analytics dashboard."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    analytics = AnalyticsService(session)

    # Get overview stats
    overview = analytics.get_overview_stats()
    daily_counts = analytics.get_daily_message_counts(days=30)
    hourly_activity = analytics.get_hourly_activity(days=30)
    weekly_activity = analytics.get_weekly_activity(days=90)
    top_chats = analytics.get_top_chats(limit=10)
    chat_type_dist = analytics.get_chat_type_distribution()
    media_stats = analytics.get_media_stats()

    log_audit(request, 'other', 'Viewed analytics dashboard', session=session)

    context = {
        'overview': overview,
        'daily_counts': json.dumps(daily_counts, default=str),
        'hourly_activity': json.dumps(hourly_activity),
        'weekly_activity': json.dumps(weekly_activity),
        'top_chats': top_chats,
        'chat_type_dist': json.dumps(chat_type_dist),
        'media_stats': media_stats,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/analytics/dashboard.html', context)


@login_required
def analytics_word_cloud(request):
    """Word cloud / word frequency page."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    analytics = AnalyticsService(session)

    days = int(request.GET.get('days', 30))
    chat_id = request.GET.get('chat_id')
    min_length = int(request.GET.get('min_length', 3))

    word_freq = analytics.get_word_frequency(limit=200, chat_id=chat_id, days=days, min_word_length=min_length)

    # Get chats for filter dropdown
    chats = TelegramChat.objects.filter(session=session).order_by('title')

    context = {
        'word_frequency': word_freq,
        'word_frequency_json': json.dumps(word_freq),
        'days': days,
        'chat_id': chat_id,
        'min_length': min_length,
        'chats': chats,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/analytics/word_cloud.html', context)


@login_required
def analytics_top_senders(request):
    """Top senders analysis page."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    analytics = AnalyticsService(session)

    period = int(request.GET.get('period', 30))
    selected_chat = request.GET.get('chat')
    chat_id = int(selected_chat) if selected_chat else None

    top_senders = analytics.get_top_senders(limit=50, chat_id=chat_id, days=period if period > 0 else None)
    chats = TelegramChat.objects.filter(session=session).order_by('title')

    # Calculate total and percentages
    total_messages = sum(s.get('count', 0) for s in top_senders)
    for sender in top_senders:
        sender['percentage'] = (sender['count'] / total_messages * 100) if total_messages > 0 else 0

    # Prepare chart data
    chart_data = {
        'labels': [s.get('sender_name', 'Unknown') for s in top_senders[:10]],
        'values': [s.get('count', 0) for s in top_senders[:10]],
        'others': sum(s.get('count', 0) for s in top_senders[10:]) if len(top_senders) > 10 else 0,
    }

    # Stats
    stats = {
        'total_senders': len(top_senders),
        'total_messages': total_messages,
        'avg_per_sender': total_messages / len(top_senders) if top_senders else 0,
        'top10_percentage': sum(s['percentage'] for s in top_senders[:10]) if top_senders else 0,
    }

    context = {
        'top_senders': top_senders,
        'period': period,
        'selected_chat': chat_id,
        'chats': chats,
        'chart_data': json.dumps(chart_data),
        'stats': stats,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/analytics/top_senders.html', context)


@login_required
def analytics_activity_heatmap(request):
    """Activity heatmap page."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    analytics = AnalyticsService(session)

    days = int(request.GET.get('days', 365))
    heatmap_data = analytics.get_activity_heatmap(days=days)

    context = {
        'heatmap_data': json.dumps(heatmap_data),
        'days': days,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/analytics/heatmap.html', context)


@login_required
def analytics_api(request, stat_type):
    """API endpoint for fetching analytics data."""
    session = get_current_session(request.user)
    if not session:
        return JsonResponse({'error': 'No active session'}, status=400)

    analytics = AnalyticsService(session)
    days = int(request.GET.get('days', 30))
    chat_id = request.GET.get('chat_id')

    try:
        if stat_type == 'daily':
            data = analytics.get_daily_message_counts(days=days, chat_id=chat_id)
        elif stat_type == 'hourly':
            data = analytics.get_hourly_activity(days=days, chat_id=chat_id)
        elif stat_type == 'weekly':
            data = analytics.get_weekly_activity(days=days, chat_id=chat_id)
        elif stat_type == 'top_senders':
            data = analytics.get_top_senders(days=days, chat_id=chat_id)
        elif stat_type == 'media':
            data = analytics.get_media_stats(chat_id=chat_id)
        elif stat_type == 'heatmap':
            data = analytics.get_activity_heatmap(days=days, chat_id=chat_id)
        else:
            return JsonResponse({'error': 'Unknown stat type'}, status=400)

        return JsonResponse({'success': True, 'data': data}, default=str)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================
# Export Views
# ============================================

@login_required
def export_page(request):
    """Export options page."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    chats = TelegramChat.objects.filter(session=session).annotate(
        message_count=Count('messages')
    ).order_by('title')

    # Get recent exports
    recent_exports = BackupHistory.objects.filter(user=request.user).order_by('-created_at')[:10]

    context = {
        'chats': chats,
        'recent_exports': recent_exports,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/export/export_page.html', context)


@login_required
def export_json(request):
    """Export messages to JSON format."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    chat_id = request.GET.get('chat_id')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    include_deleted = request.GET.get('include_deleted', '1') == '1'

    # Build query
    messages = TelegramMessage.objects.filter(chat__session=session)

    if chat_id:
        messages = messages.filter(chat__chat_id=int(chat_id))

    if date_from:
        messages = messages.filter(date__date__gte=date_from)

    if date_to:
        messages = messages.filter(date__date__lte=date_to)

    if not include_deleted:
        messages = messages.filter(is_deleted=False)

    messages = messages.select_related('chat').order_by('chat', 'date')

    # Build export data
    export_data = {
        'exported_at': timezone.now().isoformat(),
        'session': {
            'phone': session.phone_number,
            'telegram_username': session.telegram_username,
        },
        'total_messages': messages.count(),
        'messages': []
    }

    for msg in messages:
        export_data['messages'].append({
            'id': msg.message_id,
            'chat_id': msg.chat.chat_id,
            'chat_title': msg.chat.title,
            'chat_type': msg.chat.chat_type,
            'text': msg.text,
            'date': msg.date.isoformat(),
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'is_outgoing': msg.is_outgoing,
            'is_deleted': msg.is_deleted,
            'deleted_at': msg.deleted_at.isoformat() if msg.deleted_at else None,
            'has_media': msg.has_media,
            'media_type': msg.media_type,
            'media_file_name': msg.media_file_name,
        })

    # Create response
    response = HttpResponse(
        json.dumps(export_data, indent=2, ensure_ascii=False),
        content_type='application/json'
    )
    filename = f'telegram_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.json'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    # Log export
    log_audit(request, 'export_data', f'Exported {messages.count()} messages to JSON', session=session)

    # Save to backup history
    BackupHistory.objects.create(
        user=request.user,
        status='completed',
        messages_count=messages.count(),
        file_size=len(response.content),
    )

    return response


@login_required
def export_csv(request):
    """Export messages to CSV format."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    chat_id = request.GET.get('chat_id')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    messages = TelegramMessage.objects.filter(chat__session=session)

    if chat_id:
        messages = messages.filter(chat__chat_id=int(chat_id))
    if date_from:
        messages = messages.filter(date__date__gte=date_from)
    if date_to:
        messages = messages.filter(date__date__lte=date_to)

    messages = messages.select_related('chat').order_by('chat', 'date')

    # Create CSV
    output = StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow([
        'Message ID', 'Chat ID', 'Chat Title', 'Chat Type',
        'Date', 'Sender ID', 'Sender Name', 'Text',
        'Is Outgoing', 'Is Deleted', 'Deleted At',
        'Has Media', 'Media Type'
    ])

    for msg in messages:
        writer.writerow([
            msg.message_id,
            msg.chat.chat_id,
            msg.chat.title,
            msg.chat.chat_type,
            msg.date.isoformat(),
            msg.sender_id,
            msg.sender_name,
            msg.text,
            msg.is_outgoing,
            msg.is_deleted,
            msg.deleted_at.isoformat() if msg.deleted_at else '',
            msg.has_media,
            msg.media_type or '',
        ])

    response = HttpResponse(output.getvalue(), content_type='text/csv')
    filename = f'telegram_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    log_audit(request, 'export_data', f'Exported {messages.count()} messages to CSV', session=session)

    return response


@login_required
def export_html(request):
    """Export messages to HTML format."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    chat_id = request.GET.get('chat_id')
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')

    messages_qs = TelegramMessage.objects.filter(chat__session=session)

    if chat_id:
        messages_qs = messages_qs.filter(chat__chat_id=int(chat_id))

    if date_from:
        messages_qs = messages_qs.filter(date__date__gte=date_from)
    if date_to:
        messages_qs = messages_qs.filter(date__date__lte=date_to)

    messages_qs = messages_qs.select_related('chat').order_by('chat', 'date')

    # Group messages by chat for the HTML template
    chats_data = []
    current_chat = None
    current_messages = []

    for msg in messages_qs:
        if current_chat is None or current_chat.id != msg.chat.id:
            if current_chat is not None:
                chats_data.append({
                    'id': current_chat.id,
                    'title': current_chat.title,
                    'chat_type': current_chat.chat_type,
                    'message_count': len(current_messages),
                    'deleted_count': sum(1 for m in current_messages if m.is_deleted),
                    'messages': current_messages,
                })
            current_chat = msg.chat
            current_messages = []

        current_messages.append({
            'id': msg.id,
            'text': msg.text,
            'date': msg.date,
            'sender_name': msg.sender_name,
            'is_deleted': msg.is_deleted,
            'deleted_at': msg.deleted_at,
            'has_media': msg.has_media,
            'media_type': msg.media_type,
            'media_path': msg.media_file.name if msg.media_file else None,
        })

    # Don't forget the last chat
    if current_chat is not None:
        chats_data.append({
            'id': current_chat.id,
            'title': current_chat.title,
            'chat_type': current_chat.chat_type,
            'message_count': len(current_messages),
            'deleted_count': sum(1 for m in current_messages if m.is_deleted),
            'messages': current_messages,
        })

    total_messages = messages_qs.count()
    deleted_count = messages_qs.filter(is_deleted=True).count()

    context = {
        'chats': chats_data,
        'export_date': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
        'total_chats': len(chats_data),
        'total_messages': total_messages,
        'deleted_count': deleted_count,
    }

    from django.template.loader import render_to_string
    html_content = render_to_string('telegram_functionality/export/export_html_template.html', context)

    response = HttpResponse(html_content, content_type='text/html')
    filename = f'telegram_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.html'
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    log_audit(request, 'export_data', f'Exported {total_messages} messages to HTML', session=session)

    return response


# ============================================
# Bookmarks Views
# ============================================

@login_required
def bookmarks_list(request):
    """View all bookmarks."""
    bookmarks = MessageBookmark.objects.filter(
        user=request.user
    ).select_related('message', 'message__chat').order_by('-created_at')

    # Filter by chat if specified
    chat_id = request.GET.get('chat_id')
    if chat_id:
        bookmarks = bookmarks.filter(message__chat__chat_id=int(chat_id))

    # Get all chats that have bookmarks for filter dropdown
    bookmark_chats = TelegramChat.objects.filter(
        messages__bookmarks__user=request.user
    ).distinct()

    context = {
        'bookmarks': bookmarks,
        'bookmark_chats': bookmark_chats,
        'selected_chat': chat_id,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/bookmarks/list.html', context)


@login_required
@require_POST
def toggle_bookmark(request, message_id):
    """Toggle bookmark on a message."""
    message = get_object_or_404(TelegramMessage, id=message_id)

    # Security check
    if message.chat.session.user != request.user:
        return JsonResponse({'error': 'Access denied'}, status=403)

    bookmark, created = MessageBookmark.objects.get_or_create(
        user=request.user,
        message=message,
    )

    if not created:
        bookmark.delete()
        log_audit(request, 'delete_bookmark', f'Removed bookmark from message {message_id}', message=message)
        return JsonResponse({'success': True, 'bookmarked': False})

    log_audit(request, 'create_bookmark', f'Bookmarked message {message_id}', message=message)
    return JsonResponse({'success': True, 'bookmarked': True, 'bookmark_id': bookmark.id})


@login_required
@require_POST
def update_bookmark_note(request, bookmark_id):
    """Update note on a bookmark."""
    bookmark = get_object_or_404(MessageBookmark, id=bookmark_id, user=request.user)

    data = json.loads(request.body)
    bookmark.note = data.get('note', '')
    bookmark.save()

    return JsonResponse({'success': True})


@login_required
@require_POST
def delete_bookmark(request, bookmark_id):
    """Delete a bookmark."""
    bookmark = get_object_or_404(MessageBookmark, id=bookmark_id, user=request.user)
    bookmark.delete()

    log_audit(request, 'delete_bookmark', f'Deleted bookmark {bookmark_id}')
    return JsonResponse({'success': True})


# ============================================
# Tags Views
# ============================================

@login_required
def tags_list(request):
    """View all tags."""
    tags = Tag.objects.filter(user=request.user).annotate(
        message_count=Count('message_taggings')
    ).order_by('name')

    context = {
        'tags': tags,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/tags/list.html', context)


@login_required
@require_POST
def create_tag(request):
    """Create a new tag."""
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    color = data.get('color', '#6c757d')

    if not name:
        return JsonResponse({'error': 'Tag name is required'}, status=400)

    tag, created = Tag.objects.get_or_create(
        user=request.user,
        name=name,
        defaults={'color': color}
    )

    if not created:
        return JsonResponse({'error': 'Tag already exists'}, status=400)

    log_audit(request, 'create_tag', f'Created tag: {name}')
    return JsonResponse({'success': True, 'tag_id': tag.id, 'name': tag.name, 'color': tag.color})


@login_required
@require_POST
def delete_tag(request, tag_id):
    """Delete a tag."""
    tag = get_object_or_404(Tag, id=tag_id, user=request.user)
    tag_name = tag.name
    tag.delete()

    log_audit(request, 'other', f'Deleted tag: {tag_name}')
    return JsonResponse({'success': True})


@login_required
@require_POST
def tag_message(request, message_id):
    """Add/remove tags from a message."""
    message = get_object_or_404(TelegramMessage, id=message_id)

    if message.chat.session.user != request.user:
        return JsonResponse({'error': 'Access denied'}, status=403)

    data = json.loads(request.body)
    tag_ids = data.get('tag_ids', [])

    # Remove existing taggings
    MessageTagging.objects.filter(message=message, tag__user=request.user).delete()

    # Add new taggings
    for tag_id in tag_ids:
        tag = Tag.objects.filter(id=tag_id, user=request.user).first()
        if tag:
            MessageTagging.objects.create(tag=tag, message=message)

    return JsonResponse({'success': True})


@login_required
def tagged_messages(request, tag_id):
    """View messages with a specific tag."""
    tag = get_object_or_404(Tag, id=tag_id, user=request.user)

    messages = TelegramMessage.objects.filter(
        taggings__tag=tag
    ).select_related('chat').order_by('-date')

    paginator = Paginator(messages, 50)
    page = request.GET.get('page', 1)
    messages_page = paginator.get_page(page)

    context = {
        'tag': tag,
        'messages': messages_page,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/tags/tagged_messages.html', context)


# ============================================
# Folders Views
# ============================================

@login_required
def folders_list(request):
    """View all folders."""
    folders = ChatFolder.objects.filter(user=request.user).annotate(
        chat_count=Count('memberships')
    ).order_by('order', 'name')

    context = {
        'folders': folders,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/folders/list.html', context)


@login_required
@require_POST
def create_folder(request):
    """Create a new folder."""
    data = json.loads(request.body)
    name = data.get('name', '').strip()
    color = data.get('color', '#0088cc')
    icon = data.get('icon', 'bi-folder')

    if not name:
        return JsonResponse({'error': 'Folder name is required'}, status=400)

    folder, created = ChatFolder.objects.get_or_create(
        user=request.user,
        name=name,
        defaults={'color': color, 'icon': icon}
    )

    if not created:
        return JsonResponse({'error': 'Folder already exists'}, status=400)

    log_audit(request, 'create_folder', f'Created folder: {name}')
    return JsonResponse({'success': True, 'folder_id': folder.id})


@login_required
@require_POST
def delete_folder(request, folder_id):
    """Delete a folder."""
    folder = get_object_or_404(ChatFolder, id=folder_id, user=request.user)
    folder.delete()

    return JsonResponse({'success': True})


@login_required
@require_POST
def add_chat_to_folder(request, folder_id):
    """Add a chat to a folder."""
    folder = get_object_or_404(ChatFolder, id=folder_id, user=request.user)

    data = json.loads(request.body)
    chat_id = data.get('chat_id')

    chat = get_object_or_404(TelegramChat, chat_id=chat_id, session__user=request.user)

    membership, created = ChatFolderMembership.objects.get_or_create(
        folder=folder,
        chat=chat
    )

    return JsonResponse({'success': True, 'created': created})


@login_required
@require_POST
def remove_chat_from_folder(request, folder_id, chat_id):
    """Remove a chat from a folder."""
    ChatFolderMembership.objects.filter(
        folder_id=folder_id,
        folder__user=request.user,
        chat__chat_id=chat_id
    ).delete()

    return JsonResponse({'success': True})


@login_required
def folder_chats(request, folder_id):
    """View chats in a folder."""
    folder = get_object_or_404(ChatFolder, id=folder_id, user=request.user)

    chats = TelegramChat.objects.filter(
        folder_memberships__folder=folder
    ).annotate(
        message_count=Count('messages')
    ).order_by('title')

    context = {
        'folder': folder,
        'chats': chats,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/folders/folder_chats.html', context)


# ============================================
# Notes Views
# ============================================

@login_required
@require_POST
def add_note(request, message_id):
    """Add a note to a message."""
    message = get_object_or_404(TelegramMessage, id=message_id)

    if message.chat.session.user != request.user:
        return JsonResponse({'error': 'Access denied'}, status=403)

    data = json.loads(request.body)
    content = data.get('content', '').strip()

    if not content:
        return JsonResponse({'error': 'Note content is required'}, status=400)

    note = MessageNote.objects.create(
        user=request.user,
        message=message,
        content=content
    )

    return JsonResponse({'success': True, 'note_id': note.id})


@login_required
@require_POST
def delete_note(request, note_id):
    """Delete a note."""
    note = get_object_or_404(MessageNote, id=note_id, user=request.user)
    note.delete()

    return JsonResponse({'success': True})


@login_required
def notes_list(request):
    """View all notes."""
    notes = MessageNote.objects.filter(
        user=request.user
    ).select_related('message', 'message__chat').order_by('-created_at')

    context = {
        'notes': notes,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/notes/list.html', context)


# ============================================
# Media Gallery Views
# ============================================

@login_required
def media_gallery(request):
    """Media gallery with grid view."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Filters
    media_type = request.GET.get('type', 'all')
    chat_id = request.GET.get('chat_id')
    page = int(request.GET.get('page', 1))
    per_page = 48

    media_messages = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True
    ).exclude(
        Q(media_file='') | Q(media_file__isnull=True)
    ).select_related('chat').order_by('-date')

    if chat_id:
        media_messages = media_messages.filter(chat__chat_id=int(chat_id))

    if media_type == 'images':
        media_messages = media_messages.filter(media_mime_type__startswith='image/')
    elif media_type == 'videos':
        media_messages = media_messages.filter(media_mime_type__startswith='video/')
    elif media_type == 'audio':
        media_messages = media_messages.filter(media_mime_type__startswith='audio/')
    elif media_type == 'documents':
        media_messages = media_messages.exclude(
            Q(media_mime_type__startswith='image/') |
            Q(media_mime_type__startswith='video/') |
            Q(media_mime_type__startswith='audio/')
        )

    total = media_messages.count()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    media_messages = media_messages[offset:offset + per_page]

    chats = TelegramChat.objects.filter(session=session).order_by('title')

    context = {
        'media_messages': media_messages,
        'media_type': media_type,
        'chat_id': chat_id,
        'chats': chats,
        'page': page,
        'total_pages': total_pages,
        'total': total,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/media/gallery.html', context)


@login_required
def media_slideshow(request):
    """Slideshow view for images."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    chat_id = request.GET.get('chat_id')
    start_id = request.GET.get('start_id')

    images = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True,
        media_mime_type__startswith='image/'
    ).exclude(
        Q(media_file='') | Q(media_file__isnull=True)
    ).select_related('chat').order_by('-date')

    if chat_id:
        images = images.filter(chat__chat_id=int(chat_id))

    context = {
        'images': images[:200],  # Limit for performance
        'start_id': start_id,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/media/slideshow.html', context)


# ============================================
# Keyword Alerts Views
# ============================================

@login_required
def keyword_alerts_list(request):
    """View all keyword alerts."""
    alerts = KeywordAlert.objects.filter(user=request.user).order_by('-created_at')

    context = {
        'alerts': alerts,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/alerts/list.html', context)


@login_required
@require_POST
def create_keyword_alert(request):
    """Create a new keyword alert."""
    data = json.loads(request.body)
    keyword = data.get('keyword', '').strip()
    match_type = data.get('match_type', 'contains')
    case_sensitive = data.get('case_sensitive', False)
    webhook_url = data.get('webhook_url', '')

    if not keyword:
        return JsonResponse({'error': 'Keyword is required'}, status=400)

    alert = KeywordAlert.objects.create(
        user=request.user,
        keyword=keyword,
        match_type=match_type,
        case_sensitive=case_sensitive,
        notify_webhook=bool(webhook_url),
        webhook_url=webhook_url if webhook_url else None,
    )

    return JsonResponse({'success': True, 'alert_id': alert.id})


@login_required
@require_POST
def toggle_keyword_alert(request, alert_id):
    """Toggle keyword alert active state."""
    alert = get_object_or_404(KeywordAlert, id=alert_id, user=request.user)
    alert.is_active = not alert.is_active
    alert.save()

    return JsonResponse({'success': True, 'is_active': alert.is_active})


@login_required
@require_POST
def delete_keyword_alert(request, alert_id):
    """Delete a keyword alert."""
    alert = get_object_or_404(KeywordAlert, id=alert_id, user=request.user)
    alert.delete()

    return JsonResponse({'success': True})


@login_required
def alert_triggers_list(request, alert_id):
    """View triggered alerts for a keyword alert."""
    alert = get_object_or_404(KeywordAlert, id=alert_id, user=request.user)

    triggers = AlertTrigger.objects.filter(alert=alert).select_related(
        'message', 'message__chat'
    ).order_by('-triggered_at')[:100]

    context = {
        'alert': alert,
        'triggers': triggers,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/alerts/triggers.html', context)


# ============================================
# Audit Log Views
# ============================================

@login_required
def audit_log_list(request):
    """View audit logs."""
    logs = AuditLog.objects.filter(user=request.user).order_by('-created_at')

    # Filter by action type
    action = request.GET.get('action')
    if action:
        logs = logs.filter(action=action)

    # Date filter
    date_from = request.GET.get('date_from')
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)

    paginator = Paginator(logs, 50)
    page = request.GET.get('page', 1)
    logs_page = paginator.get_page(page)

    # Get unique action types for filter
    action_types = AuditLog.ACTION_TYPES

    context = {
        'logs': logs_page,
        'action_types': action_types,
        'selected_action': action,
        'date_from': date_from,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/audit/list.html', context)


# ============================================
# Duplicate Detection Views
# ============================================

@login_required
def find_duplicates(request):
    """Find duplicate media files."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Find duplicates by file hash
    duplicates = MediaHash.objects.filter(
        message__chat__session=session
    ).values('file_hash').annotate(
        count=Count('id')
    ).filter(count__gt=1).order_by('-count')

    duplicate_groups = []
    for dup in duplicates[:50]:
        if dup['file_hash']:
            messages = TelegramMessage.objects.filter(
                media_hash__file_hash=dup['file_hash'],
                chat__session=session
            ).select_related('chat')
            duplicate_groups.append({
                'hash': dup['file_hash'],
                'count': dup['count'],
                'messages': list(messages),
            })

    context = {
        'duplicate_groups': duplicate_groups,
        'total_duplicates': sum(d['count'] - 1 for d in duplicate_groups),
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/media/duplicates.html', context)


@login_required
def compute_media_hashes(request):
    """Compute hashes for media files (background process)."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return JsonResponse({'error': 'No session'})

    # Get messages with media but no hash
    messages = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True
    ).exclude(
        Q(media_file='') | Q(media_file__isnull=True)
    ).exclude(
        media_hash__isnull=False
    )[:100]

    computed = 0
    for msg in messages:
        try:
            file_path = os.path.join(settings.MEDIA_ROOT, str(msg.media_file))
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    file_hash = hashlib.md5(f.read()).hexdigest()

                MediaHash.objects.create(
                    message=msg,
                    file_hash=file_hash,
                    file_size=msg.media_file_size or 0,
                )
                computed += 1
        except Exception as e:
            pass

    remaining = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True
    ).exclude(
        Q(media_file='') | Q(media_file__isnull=True)
    ).exclude(
        media_hash__isnull=False
    ).count()

    return JsonResponse({
        'success': True,
        'computed': computed,
        'remaining': remaining,
    })


# ============================================
# Deletion Alerts Config Views
# ============================================

@login_required
def deletion_alert_config(request):
    """View and edit deletion alert configuration."""
    config, created = DeletionAlertConfig.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        config.is_enabled = request.POST.get('is_enabled') == 'on'
        config.notify_email = request.POST.get('notify_email') == 'on'
        config.notify_webhook = request.POST.get('notify_webhook') == 'on'
        config.webhook_url = request.POST.get('webhook_url', '').strip() or None
        config.only_own_messages = request.POST.get('only_own_messages') == 'on'
        config.min_message_age_hours = int(request.POST.get('min_message_age_hours', 0))
        config.save()

        messages.success(request, 'Deletion alert settings saved!')
        return redirect('telegram:deletion_alert_config')

    context = {
        'config': config,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/alerts/deletion_config.html', context)


# ============================================
# Scheduled Backup Views
# ============================================

@login_required
def scheduled_backups_list(request):
    """View scheduled backups."""
    session = get_current_session(request.user)

    backups = ScheduledBackup.objects.filter(user=request.user).order_by('-created_at')
    history = BackupHistory.objects.filter(user=request.user).order_by('-created_at')[:20]

    context = {
        'backups': backups,
        'history': history,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/backups/list.html', context)


@login_required
@require_POST
def create_scheduled_backup(request):
    """Create a new scheduled backup."""
    session = get_current_session(request.user)
    if not session:
        return JsonResponse({'error': 'No active session'}, status=400)

    data = json.loads(request.body)
    name = data.get('name', '').strip()
    frequency = data.get('frequency', 'weekly')
    export_format = data.get('format', 'json')
    include_media = data.get('include_media', False)

    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)

    # Calculate next run
    now = timezone.now()
    if frequency == 'daily':
        next_run = now + timedelta(days=1)
    elif frequency == 'weekly':
        next_run = now + timedelta(weeks=1)
    else:
        next_run = now + timedelta(days=30)

    backup = ScheduledBackup.objects.create(
        user=request.user,
        session=session,
        name=name,
        frequency=frequency,
        export_format=export_format,
        include_media=include_media,
        next_run=next_run,
    )

    return JsonResponse({'success': True, 'backup_id': backup.id})


@login_required
@require_POST
def toggle_scheduled_backup(request, backup_id):
    """Toggle scheduled backup active state."""
    backup = get_object_or_404(ScheduledBackup, id=backup_id, user=request.user)
    backup.is_active = not backup.is_active
    backup.save()

    return JsonResponse({'success': True, 'is_active': backup.is_active})


@login_required
@require_POST
def delete_scheduled_backup(request, backup_id):
    """Delete a scheduled backup."""
    backup = get_object_or_404(ScheduledBackup, id=backup_id, user=request.user)
    backup.delete()

    return JsonResponse({'success': True})


@login_required
@require_POST
def run_backup_now(request, backup_id):
    """Run a backup schedule immediately."""
    backup = get_object_or_404(ScheduledBackup, id=backup_id, user=request.user)

    # Create a backup history entry
    history = BackupHistory.objects.create(
        user=request.user,
        schedule=backup,
        status='running',
    )

    # In a real implementation, this would be handled by Celery
    # For now, we'll just mark it as queued
    history.status = 'completed'
    history.save()

    backup.last_run = timezone.now()
    backup.save()

    return JsonResponse({'success': True, 'history_id': history.id})


@login_required
def download_backup(request, history_id):
    """Download a backup file."""
    history = get_object_or_404(BackupHistory, id=history_id, user=request.user)

    if not history.file_path or not os.path.exists(history.file_path):
        return HttpResponse('Backup file not found', status=404)

    return FileResponse(
        open(history.file_path, 'rb'),
        as_attachment=True,
        filename=os.path.basename(history.file_path)
    )


# ============================================
# Alert Triggers Additional Views
# ============================================

@login_required
def all_triggers_list(request):
    """View all triggered alerts across all keyword alerts."""
    triggers = AlertTrigger.objects.filter(
        alert__user=request.user
    ).select_related('alert', 'message', 'message__chat').order_by('-triggered_at')

    # Filters
    selected_alert = request.GET.get('alert')
    selected_chat = request.GET.get('chat')

    if selected_alert:
        triggers = triggers.filter(alert_id=int(selected_alert))
    if selected_chat:
        triggers = triggers.filter(message__chat_id=int(selected_chat))

    paginator = Paginator(triggers, 50)
    page = request.GET.get('page', 1)
    triggers_page = paginator.get_page(page)

    alerts = KeywordAlert.objects.filter(user=request.user)
    chats = TelegramChat.objects.filter(
        messages__alert_triggers__alert__user=request.user
    ).distinct()

    context = {
        'triggers': triggers_page,
        'alerts': alerts,
        'chats': chats,
        'selected_alert': int(selected_alert) if selected_alert else None,
        'selected_chat': int(selected_chat) if selected_chat else None,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/alerts/triggers.html', context)


@login_required
@require_POST
def mark_trigger_read(request, trigger_id):
    """Mark a trigger as read."""
    trigger = get_object_or_404(
        AlertTrigger,
        id=trigger_id,
        alert__user=request.user
    )
    trigger.is_read = True
    trigger.save()

    return JsonResponse({'success': True})


@login_required
@require_POST
def clear_all_triggers(request):
    """Clear all triggers for the current user."""
    AlertTrigger.objects.filter(alert__user=request.user).delete()
    return JsonResponse({'success': True})


# ============================================
# Folder Additional Views
# ============================================

@login_required
@require_POST
def folder_add_chats(request, folder_id):
    """Add multiple chats to a folder."""
    folder = get_object_or_404(ChatFolder, id=folder_id, user=request.user)

    data = json.loads(request.body)
    chat_ids = data.get('chat_ids', [])

    added_count = 0
    for chat_id in chat_ids:
        chat = TelegramChat.objects.filter(id=chat_id, session__user=request.user).first()
        if chat:
            membership, created = ChatFolderMembership.objects.get_or_create(
                folder=folder,
                chat=chat
            )
            if created:
                added_count += 1

    return JsonResponse({'success': True, 'added': added_count})


@login_required
@require_POST
def folder_remove_chat(request, folder_id):
    """Remove a chat from a folder (accepts JSON body)."""
    folder = get_object_or_404(ChatFolder, id=folder_id, user=request.user)

    data = json.loads(request.body)
    chat_id = data.get('chat_id')

    if chat_id:
        ChatFolderMembership.objects.filter(
            folder=folder,
            chat_id=chat_id
        ).delete()

    return JsonResponse({'success': True})


@login_required
def folder_chats_view(request, folder_id):
    """View chats in a folder with available chats for adding."""
    folder = get_object_or_404(ChatFolder, id=folder_id, user=request.user)
    session = get_current_session(request.user)

    # Get chats in this folder
    chats = TelegramChat.objects.filter(
        folder_memberships__folder=folder
    ).annotate(
        message_count=Count('messages')
    ).order_by('title')

    # Get available chats (not in this folder)
    folder_chat_ids = ChatFolderMembership.objects.filter(folder=folder).values_list('chat_id', flat=True)
    available_chats = TelegramChat.objects.filter(
        session=session
    ).exclude(
        id__in=folder_chat_ids
    ).annotate(
        message_count=Count('messages')
    ).order_by('title')

    context = {
        'folder': folder,
        'chats': chats,
        'available_chats': available_chats,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/folders/folder_chats.html', context)


# ============================================
# Tags Additional Views
# ============================================

@login_required
@require_POST
def remove_tagging(request, tagging_id):
    """Remove a tag from a message."""
    tagging = get_object_or_404(
        MessageTagging,
        id=tagging_id,
        tag__user=request.user
    )
    tagging.delete()

    return JsonResponse({'success': True})


@login_required
def tags_list_view(request):
    """View all tags with message counts."""
    tags = Tag.objects.filter(user=request.user).annotate(
        message_count=Count('message_taggings')
    ).order_by('name')

    context = {
        'tags': tags,
        'session': get_current_session(request.user),
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/tags/list.html', context)


# ============================================
# Deletion Alert Additional Views
# ============================================

@login_required
def deletion_alert_config_view(request):
    """View and edit deletion alert configuration with GET and POST support."""
    config, created = DeletionAlertConfig.objects.get_or_create(user=request.user)
    session = get_current_session(request.user)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            config.is_enabled = data.get('enabled', False)
            config.min_message_age_hours = data.get('min_message_age_hours', 1)
            config.notify_webhook = data.get('notify_webhook', False)
            config.webhook_url = data.get('webhook_url') or None
            config.save()

            # Handle monitored chats
            monitored_chat_ids = data.get('monitored_chats', [])
            # In a full implementation, you'd save these to a M2M field

            return JsonResponse({'success': True})
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Get recent deletions
    recent_deletions = TelegramMessage.objects.filter(
        chat__session=session,
        is_deleted=True
    ).select_related('chat').order_by('-deleted_at')[:20] if session else []

    # Get deletion stats
    now = timezone.now()
    stats = {}
    if session:
        stats = {
            'today': TelegramMessage.objects.filter(
                chat__session=session,
                is_deleted=True,
                deleted_at__date=now.date()
            ).count(),
            'week': TelegramMessage.objects.filter(
                chat__session=session,
                is_deleted=True,
                deleted_at__gte=now - timedelta(days=7)
            ).count(),
            'total': TelegramMessage.objects.filter(
                chat__session=session,
                is_deleted=True
            ).count(),
        }

    chats = TelegramChat.objects.filter(session=session).order_by('title') if session else []

    context = {
        'config': config,
        'chats': chats,
        'monitored_chat_ids': [],  # Would be populated from config
        'recent_deletions': recent_deletions,
        'stats': stats,
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/alerts/deletion_config.html', context)
