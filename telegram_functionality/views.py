import os
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, FileResponse, Http404
from django.utils import timezone
from django.db.models import Q
from django.conf import settings

from .forms import PhoneNumberForm, VerificationCodeForm, TwoFactorForm, AdvancedSearchForm
from .models import TelegramSession, TelegramChat, TelegramMessage, SyncTask
from .services import telegram_manager, start_background_sync

# Logging imports
from telegram_analyzer_app.logging_utils import (
    telegram_views_logger as logger,
    security_logger,
    log_view,
    log_user_action,
    log_security_event,
    log_telegram_connection,
    get_client_ip,
)


def get_current_session(user):
    """
    Get the current active session for a user.
    Returns the session marked as current, or the first active session,
    or None if no sessions exist.
    """
    # First try to get the session marked as current
    session = TelegramSession.objects.filter(user=user, is_current=True, is_active=True).first()
    if session:
        return session

    # Fall back to the first active session
    session = TelegramSession.objects.filter(user=user, is_active=True).first()
    if session:
        # Mark it as current
        session.set_as_current()
        return session

    # Return any session (even inactive) for display purposes
    return TelegramSession.objects.filter(user=user).first()


def get_session_or_redirect(request):
    """
    Get current session or return redirect response.
    Returns (session, None) if session found, or (None, redirect_response) if not.
    """
    session = get_current_session(request.user)
    if not session:
        return None, redirect('telegram:connect')
    if not session.is_active:
        return None, redirect('telegram:connect')
    return session, None


def get_all_user_sessions(user):
    """Get all sessions for a user, ordered by current status and created date."""
    return TelegramSession.objects.filter(user=user).order_by('-is_current', '-created_at')


def home(request):
    """Home page view."""
    return render(request, 'telegram_functionality/home.html')


@login_required
def download_media(request, message_id):
    """Download or serve media file for a message."""
    message = get_object_or_404(TelegramMessage, id=message_id)

    # Security check: ensure user owns this message
    if message.chat.session.user != request.user:
        raise Http404("Media not found")

    if not message.media_file:
        raise Http404("No media file available")

    # Get the full file path
    file_path = os.path.join(settings.MEDIA_ROOT, str(message.media_file))

    if not os.path.exists(file_path):
        raise Http404("Media file not found on disk")

    # Determine content type
    content_type, _ = mimetypes.guess_type(file_path)
    if not content_type:
        content_type = 'application/octet-stream'

    # Determine if this should be displayed inline (images) or downloaded
    disposition = 'inline' if content_type.startswith('image/') else 'attachment'
    filename = message.media_file_name or os.path.basename(file_path)

    response = FileResponse(
        open(file_path, 'rb'),
        content_type=content_type
    )
    response['Content-Disposition'] = f'{disposition}; filename="{filename}"'

    return response


@login_required
@log_view()
def telegram_connect(request):
    """View to start Telegram connection process for a new phone number."""
    logger.debug(f"telegram_connect called by user {request.user.id}")

    # Get existing sessions for display
    existing_sessions = get_all_user_sessions(request.user)

    # Check if user wants to add a new session (via query param) or has no sessions
    adding_new = request.GET.get('new') == '1'

    if existing_sessions.filter(is_active=True).exists() and not adding_new:
        # User has active sessions and isn't explicitly adding new, redirect to sessions list
        logger.info(f"User {request.user.id} has active sessions, showing sessions list")
        return redirect('telegram:sessions')

    if request.method == 'POST':
        form = PhoneNumberForm(request.POST)
        if form.is_valid():
            phone_number = form.cleaned_data['phone_number']
            logger.info(f"User {request.user.id} requesting verification code for phone: {phone_number[:4]}****")

            # Send verification code
            result = telegram_manager.send_code(phone_number)

            if result['success']:
                # Store data in session for next step
                request.session['telegram_phone'] = phone_number
                request.session['telegram_phone_code_hash'] = result['phone_code_hash']
                request.session['telegram_session_string'] = result['session_string']
                log_telegram_connection(request.user, phone_number, "code_sent")
                logger.info(f"Verification code sent successfully for user {request.user.id}")
                return redirect('telegram:verify_code')
            else:
                error_msg = result.get('error', 'Failed to send code')
                logger.warning(f"Failed to send verification code for user {request.user.id}: {error_msg}")
                log_security_event("telegram_code_failed", request.user, get_client_ip(request), error_msg)
                messages.error(request, error_msg)
    else:
        form = PhoneNumberForm()

    return render(request, 'telegram_functionality/connect.html', {
        'form': form,
        'existing_sessions': existing_sessions,
        'adding_new': adding_new,
    })


@login_required
@log_view()
def verify_code(request):
    """View to verify the code sent to phone."""
    logger.debug(f"verify_code called by user {request.user.id}")

    # Check if we have the required session data
    if 'telegram_phone' not in request.session:
        logger.warning(f"User {request.user.id} attempted verify_code without phone in session")
        messages.error(request, 'Please enter your phone number first.')
        return redirect('telegram:connect')

    phone_number = request.session['telegram_phone']

    if request.method == 'POST':
        form = VerificationCodeForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']
            logger.info(f"User {request.user.id} attempting to verify code")

            result = telegram_manager.verify_code(
                session_string=request.session['telegram_session_string'],
                phone_number=phone_number,
                phone_code_hash=request.session['telegram_phone_code_hash'],
                code=code
            )

            if result['success']:
                if result.get('requires_2fa'):
                    # User has 2FA enabled
                    logger.info(f"User {request.user.id} requires 2FA verification")
                    request.session['telegram_session_string'] = result['session_string']
                    return redirect('telegram:verify_2fa')
                else:
                    # Successfully logged in
                    _save_telegram_session(request, result)
                    _clear_telegram_session_data(request)
                    log_telegram_connection(request.user, phone_number, "connected", f"Telegram User ID: {result.get('user_id')}")
                    log_user_action(request.user, "telegram_connected", f"Phone: {phone_number[:4]}****")
                    logger.info(f"User {request.user.id} successfully connected to Telegram")
                    messages.success(request, 'Successfully connected to Telegram!')
                    return redirect('telegram:dashboard')
            else:
                error_msg = result.get('error', 'Verification failed')
                logger.warning(f"Code verification failed for user {request.user.id}: {error_msg}")
                log_security_event("telegram_verify_failed", request.user, get_client_ip(request), error_msg)
                messages.error(request, error_msg)
    else:
        form = VerificationCodeForm()

    return render(request, 'telegram_functionality/verify_code.html', {
        'form': form,
        'phone_number': phone_number,
    })


@login_required
@log_view()
def verify_2fa(request):
    """View to verify 2FA password."""
    logger.debug(f"verify_2fa called by user {request.user.id}")

    if 'telegram_session_string' not in request.session:
        logger.warning(f"User {request.user.id} attempted verify_2fa without session string")
        messages.error(request, 'Please start the connection process again.')
        return redirect('telegram:connect')

    if request.method == 'POST':
        form = TwoFactorForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data['password']
            logger.info(f"User {request.user.id} attempting 2FA verification")

            result = telegram_manager.verify_2fa(
                session_string=request.session['telegram_session_string'],
                password=password
            )

            if result['success']:
                _save_telegram_session(request, result)
                _clear_telegram_session_data(request)
                phone_number = request.session.get('telegram_phone', 'unknown')
                log_telegram_connection(request.user, phone_number, "connected_2fa", f"Telegram User ID: {result.get('user_id')}")
                log_user_action(request.user, "telegram_connected_2fa")
                logger.info(f"User {request.user.id} successfully connected to Telegram via 2FA")
                messages.success(request, 'Successfully connected to Telegram!')
                return redirect('telegram:dashboard')
            else:
                error_msg = result.get('error', '2FA verification failed')
                logger.warning(f"2FA verification failed for user {request.user.id}: {error_msg}")
                log_security_event("telegram_2fa_failed", request.user, get_client_ip(request), error_msg)
                messages.error(request, error_msg)
    else:
        form = TwoFactorForm()

    return render(request, 'telegram_functionality/verify_2fa.html', {'form': form})


@login_required
def telegram_dashboard(request):
    """Dashboard showing Telegram connection status and chats."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    chats = session.chats.all()[:20]

    # Calculate stats
    stats = {
        'users': session.chats.filter(chat_type='user').count(),
        'groups': session.chats.filter(chat_type__in=['group', 'supergroup']).count(),
        'channels': session.chats.filter(chat_type='channel').count(),
    }

    # Get all sessions for session switcher
    all_sessions = get_all_user_sessions(request.user)

    context = {
        'session': session,
        'all_sessions': all_sessions,
        'chats': chats,
        'stats': stats,
    }
    return render(request, 'telegram_functionality/dashboard.html', context)


@login_required
def telegram_disconnect(request, session_id=None):
    """Disconnect a specific Telegram session or the current one."""
    if request.method == 'POST':
        if session_id:
            # Disconnect specific session
            session = get_object_or_404(TelegramSession, id=session_id, user=request.user)
        else:
            # Disconnect current session
            session = get_current_session(request.user)

        if session:
            session_string = session.get_session_string()
            was_current = session.is_current

            if session_string:
                telegram_manager.disconnect_session(session_string)

            session.delete()
            messages.success(request, f'Session "{session.get_display_name()}" disconnected.')

            # If we deleted the current session, set another as current
            if was_current:
                next_session = TelegramSession.objects.filter(
                    user=request.user, is_active=True
                ).first()
                if next_session:
                    next_session.set_as_current()
        else:
            messages.info(request, 'No Telegram session found.')

    # Redirect to sessions list if we have more sessions, otherwise to connect
    if TelegramSession.objects.filter(user=request.user).exists():
        return redirect('telegram:sessions')
    return redirect('telegram:connect')


@login_required
def sync_chats(request):
    """Sync user's Telegram chats."""
    session = get_current_session(request.user)
    if not session or not session.is_active:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Session not active'})
        messages.error(request, 'No active Telegram session found.')
        return redirect('telegram:connect')

    session_string = session.get_session_string()
    result = telegram_manager.get_dialogs(session_string)

    if result['success']:
        from .models import TelegramChat

        # Update or create chats
        for dialog in result['dialogs']:
            TelegramChat.objects.update_or_create(
                session=session,
                chat_id=dialog['id'],
                defaults={
                    'chat_type': dialog['type'],
                    'title': dialog['title'],
                    'username': dialog.get('username'),
                    'is_archived': dialog.get('is_archived', False),
                }
            )

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'count': len(result['dialogs'])})

        messages.success(request, f'Synced {len(result["dialogs"])} chats.')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': result.get('error')})
        messages.error(request, result.get('error', 'Failed to sync chats'))

    return redirect('telegram:dashboard')


@login_required
def resend_code(request):
    """Resend verification code."""
    if 'telegram_phone' not in request.session:
        return JsonResponse({'success': False, 'error': 'No phone number found'})

    phone_number = request.session['telegram_phone']
    result = telegram_manager.send_code(phone_number)

    if result['success']:
        request.session['telegram_phone_code_hash'] = result['phone_code_hash']
        request.session['telegram_session_string'] = result['session_string']
        return JsonResponse({'success': True, 'message': 'Code resent successfully'})

    return JsonResponse({'success': False, 'error': result.get('error', 'Failed to resend code')})


def _save_telegram_session(request, result):
    """Save Telegram session to database. Creates new or updates existing for same phone."""
    phone_number = request.session.get('telegram_phone', '')

    # Check if session with this phone number already exists for user
    session, created = TelegramSession.objects.update_or_create(
        user=request.user,
        phone_number=phone_number,
        defaults={
            'telegram_user_id': result.get('user_id'),
            'telegram_username': result.get('username'),
            'telegram_first_name': result.get('first_name'),
            'telegram_last_name': result.get('last_name'),
            'is_active': True,
        }
    )
    session.set_session_string(result['session_string'])
    session.save()

    # Set this as the current session
    session.set_as_current()


def _clear_telegram_session_data(request):
    """Clear temporary Telegram data from Django session."""
    keys_to_remove = [
        'telegram_phone',
        'telegram_phone_code_hash',
        'telegram_session_string',
    ]
    for key in keys_to_remove:
        request.session.pop(key, None)


@login_required
def chat_list(request):
    """View all chats from database."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Filter by type if requested
    chat_type = request.GET.get('type', 'all')
    chats = TelegramChat.objects.filter(session=session)

    if chat_type != 'all':
        if chat_type == 'groups':
            chats = chats.filter(chat_type__in=['group', 'supergroup'])
        elif chat_type == 'channels':
            chats = chats.filter(chat_type='channel')
        elif chat_type == 'users':
            chats = chats.filter(chat_type='user')

    # Order by last synced
    chats = chats.order_by('-last_synced')

    # Convert to list of dicts for template compatibility
    chat_list = []
    for chat in chats:
        last_message = chat.messages.first()
        chat_list.append({
            'id': chat.chat_id,
            'title': chat.title,
            'type': chat.chat_type,
            'username': chat.username,
            'members_count': chat.members_count,
            'is_archived': chat.is_archived,
            'is_pinned': chat.is_pinned,
            'unread_count': 0,
            'last_message': {
                'text': last_message.text[:100] if last_message else '',
                'date': last_message.date.isoformat() if last_message else None,
            } if last_message else None,
            'total_messages': chat.total_messages,
            'last_synced': chat.last_synced,
        })

    total = TelegramChat.objects.filter(session=session).count()
    all_sessions = get_all_user_sessions(request.user)

    context = {
        'chats': chat_list,
        'total': total,
        'current_filter': chat_type,
        'session': session,
        'all_sessions': all_sessions,
        'needs_sync': total == 0,
    }
    return render(request, 'telegram_functionality/chat_list.html', context)


@login_required
def chat_messages(request, chat_id):
    """View messages from database for a specific chat."""
    chat_id = int(chat_id)  # Convert from string (re_path passes as string)
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Get chat from database
    try:
        chat = TelegramChat.objects.get(session=session, chat_id=chat_id)
    except TelegramChat.DoesNotExist:
        messages.error(request, 'Chat not found. Please sync your chats first.')
        return redirect('telegram:chats')

    # Get messages from database
    show_deleted = request.GET.get('show_deleted', 'false') == 'true'
    chat_messages_qs = TelegramMessage.objects.filter(chat=chat)

    if not show_deleted:
        chat_messages_qs = chat_messages_qs.filter(is_deleted=False)

    chat_messages_qs = chat_messages_qs.order_by('-date')

    # Pagination
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('limit', 50))
    offset = (page - 1) * per_page
    total_messages = chat_messages_qs.count()
    total_pages = (total_messages + per_page - 1) // per_page

    message_list = chat_messages_qs[offset:offset + per_page]

    # Convert to list of dicts for template compatibility
    msg_list = []
    for msg in message_list:
        msg_list.append({
            'id': msg.message_id,
            'text': msg.text,
            'date': msg.date.isoformat() if msg.date else None,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'is_outgoing': msg.is_outgoing,
            'has_media': msg.has_media,
            'media_type': msg.media_type,
            'reply_to_msg_id': msg.reply_to_msg_id,
            'forwards': msg.forwards,
            'views': msg.views,
            'is_deleted': msg.is_deleted,
            'deleted_at': msg.deleted_at.isoformat() if msg.deleted_at else None,
        })

    # Count deleted messages in this chat
    deleted_count = TelegramMessage.objects.filter(chat=chat, is_deleted=True).count()
    all_sessions = get_all_user_sessions(request.user)

    context = {
        'chat': {
            'id': chat.chat_id,
            'title': chat.title,
            'type': chat.chat_type,
            'username': chat.username,
            'members_count': chat.members_count,
        },
        'chat_messages': msg_list,
        'chat_id': chat_id,
        'total_messages': total_messages,
        'deleted_count': deleted_count,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'show_deleted': show_deleted,
        'session': session,
        'all_sessions': all_sessions,
        'last_synced': chat.last_synced,
    }
    return render(request, 'telegram_functionality/chat_messages.html', context)


@login_required
def load_more_messages(request, chat_id):
    """Load more messages (AJAX endpoint)."""
    chat_id = int(chat_id)  # Convert from string (re_path passes as string)
    session = get_current_session(request.user)
    if not session or not session.is_active:
        return JsonResponse({'success': False, 'error': 'Session not active'})

    session_string = session.get_session_string()
    offset_id = int(request.GET.get('offset_id', 0))
    limit = int(request.GET.get('limit', 50))

    result = telegram_manager.get_messages(session_string, chat_id, limit=limit, offset_id=offset_id)
    return JsonResponse(result)


@login_required
def all_messages(request):
    """View all messages from database."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Get parameters
    show_deleted = request.GET.get('show_deleted', 'false') == 'true'
    per_page = int(request.GET.get('limit', 50))
    page = int(request.GET.get('page', 1))

    # Get all messages from database
    all_msgs = TelegramMessage.objects.filter(
        chat__session=session
    ).select_related('chat').order_by('-date')

    if not show_deleted:
        all_msgs = all_msgs.filter(is_deleted=False)

    # Pagination
    total = all_msgs.count()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    message_list = all_msgs[offset:offset + per_page]

    # Convert to list of dicts
    msg_list = []
    for msg in message_list:
        msg_list.append({
            'id': msg.message_id,
            'chat_id': msg.chat.chat_id,
            'chat_title': msg.chat.title,
            'chat_type': msg.chat.chat_type,
            'text': msg.text,
            'date': msg.date.isoformat() if msg.date else None,
            'sender_id': msg.sender_id,
            'sender_name': msg.sender_name,
            'is_outgoing': msg.is_outgoing,
            'has_media': msg.has_media,
            'media_type': msg.media_type,
            'is_deleted': msg.is_deleted,
        })

    # Get stats
    total_chats = TelegramChat.objects.filter(session=session).count()
    deleted_count = TelegramMessage.objects.filter(
        chat__session=session, is_deleted=True
    ).count()
    all_sessions = get_all_user_sessions(request.user)

    context = {
        'telegram_messages': msg_list,
        'total': total,
        'total_chats': total_chats,
        'deleted_count': deleted_count,
        'page': page,
        'per_page': per_page,
        'total_pages': total_pages,
        'show_deleted': show_deleted,
        'session': session,
        'all_sessions': all_sessions,
    }
    return render(request, 'telegram_functionality/all_messages.html', context)


@login_required
def sync_all_chats(request):
    """Sync all chats and their messages to database."""
    session = get_current_session(request.user)
    if not session or not session.is_active:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'Session not active'})
        return redirect('telegram:connect')

    session_string = session.get_session_string()

    # First, sync chats list
    result = telegram_manager.get_all_chats(session_string)
    if not result['success']:
        return JsonResponse({'success': False, 'error': result.get('error')})

    synced_chats = 0
    synced_messages = 0

    for dialog in result['chats']:
        # Create or update chat
        chat, created = TelegramChat.objects.update_or_create(
            session=session,
            chat_id=dialog['id'],
            defaults={
                'chat_type': dialog['type'],
                'title': dialog['title'],
                'username': dialog.get('username'),
                'members_count': dialog.get('members_count'),
                'is_archived': dialog.get('is_archived', False),
                'is_pinned': dialog.get('is_pinned', False),
            }
        )
        synced_chats += 1

        # Fetch all messages for this chat
        min_id = chat.last_message_id or 0
        msg_result = telegram_manager.fetch_all_messages_from_chat(
            session_string, dialog['id'], min_id=min_id
        )

        if msg_result['success']:
            for msg_data in msg_result['messages']:
                TelegramMessage.objects.update_or_create(
                    chat=chat,
                    message_id=msg_data['id'],
                    defaults={
                        'text': msg_data['text'],
                        'date': msg_data['date'],
                        'sender_id': msg_data['sender_id'],
                        'sender_name': msg_data['sender_name'],
                        'is_outgoing': msg_data['is_outgoing'],
                        'has_media': msg_data['has_media'],
                        'media_type': msg_data['media_type'],
                        'reply_to_msg_id': msg_data['reply_to_msg_id'],
                        'forwards': msg_data['forwards'],
                        'views': msg_data['views'],
                    }
                )
                synced_messages += 1

            # Update chat's last message ID
            if msg_result['messages']:
                max_id = max(m['id'] for m in msg_result['messages'])
                chat.last_message_id = max_id
                chat.last_full_sync = timezone.now()
                chat.total_messages = chat.messages.count()
                chat.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': True,
            'chats': synced_chats,
            'messages': synced_messages
        })

    messages.success(request, f'Synced {synced_chats} chats and {synced_messages} messages.')
    return redirect('telegram:dashboard')


@login_required
def sync_chat_messages(request, chat_id):
    """Sync messages for a specific chat."""
    chat_id = int(chat_id)
    session = get_current_session(request.user)
    if not session or not session.is_active:
        return JsonResponse({'success': False, 'error': 'Session not active'})

    session_string = session.get_session_string()

    # Get or create chat
    try:
        chat = TelegramChat.objects.get(session=session, chat_id=chat_id)
    except TelegramChat.DoesNotExist:
        # Fetch chat info first
        chat_result = telegram_manager.get_chat_info(session_string, chat_id)
        if not chat_result['success']:
            return JsonResponse({'success': False, 'error': 'Chat not found'})

        chat = TelegramChat.objects.create(
            session=session,
            chat_id=chat_id,
            chat_type=chat_result['chat']['type'],
            title=chat_result['chat']['title'],
            username=chat_result['chat'].get('username'),
            members_count=chat_result['chat'].get('members_count'),
        )

    # Fetch all messages (incremental if we have last_message_id)
    min_id = chat.last_message_id or 0
    result = telegram_manager.fetch_all_messages_from_chat(
        session_string, chat_id, min_id=min_id
    )

    if not result['success']:
        return JsonResponse({'success': False, 'error': result.get('error')})

    synced = 0
    for msg_data in result['messages']:
        TelegramMessage.objects.update_or_create(
            chat=chat,
            message_id=msg_data['id'],
            defaults={
                'text': msg_data['text'],
                'date': msg_data['date'],
                'sender_id': msg_data['sender_id'],
                'sender_name': msg_data['sender_name'],
                'is_outgoing': msg_data['is_outgoing'],
                'has_media': msg_data['has_media'],
                'media_type': msg_data['media_type'],
                'reply_to_msg_id': msg_data['reply_to_msg_id'],
                'forwards': msg_data['forwards'],
                'views': msg_data['views'],
            }
        )
        synced += 1

    # Update chat metadata
    if result['messages']:
        max_id = max(m['id'] for m in result['messages'])
        chat.last_message_id = max_id
    chat.last_full_sync = timezone.now()
    chat.total_messages = chat.messages.count()
    chat.save()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'synced': synced})

    messages.success(request, f'Synced {synced} messages.')
    return redirect('telegram:chat_messages', chat_id=chat_id)


@login_required
def check_deleted_messages(request, chat_id=None):
    """Check for deleted messages by comparing DB with Telegram API."""
    session = get_current_session(request.user)
    if not session or not session.is_active:
        return JsonResponse({'success': False, 'error': 'Session not active'})

    session_string = session.get_session_string()
    deleted_count = 0

    if chat_id:
        chat_id = int(chat_id)
        chats = TelegramChat.objects.filter(session=session, chat_id=chat_id)
    else:
        chats = TelegramChat.objects.filter(session=session)

    for chat in chats:
        # Get current message IDs from Telegram
        result = telegram_manager.get_message_ids_from_chat(
            session_string, chat.chat_id
        )

        if not result['success']:
            continue

        telegram_ids = result['message_ids']

        # Get message IDs we have in database (not already marked deleted)
        db_messages = TelegramMessage.objects.filter(
            chat=chat, is_deleted=False
        )

        for msg in db_messages:
            if msg.message_id not in telegram_ids:
                # Message was deleted from Telegram
                msg.is_deleted = True
                msg.deleted_at = timezone.now()
                msg.save()
                deleted_count += 1

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'deleted_found': deleted_count})

    if deleted_count > 0:
        messages.info(request, f'Found {deleted_count} deleted messages.')
    else:
        messages.info(request, 'No deleted messages found.')

    return redirect('telegram:deleted_messages')


@login_required
def deleted_messages(request):
    """View all deleted messages."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Get filter parameters
    chat_id = request.GET.get('chat_id')

    deleted_msgs = TelegramMessage.objects.filter(
        chat__session=session,
        is_deleted=True
    ).select_related('chat').order_by('-deleted_at')

    if chat_id:
        deleted_msgs = deleted_msgs.filter(chat__chat_id=int(chat_id))

    # Get chats with deleted messages for filter dropdown
    chats_with_deleted = TelegramChat.objects.filter(
        session=session,
        messages__is_deleted=True
    ).distinct()

    all_sessions = get_all_user_sessions(request.user)

    context = {
        'deleted_messages': deleted_msgs,
        'chats_with_deleted': chats_with_deleted,
        'selected_chat_id': chat_id,
        'total_deleted': deleted_msgs.count(),
        'session': session,
        'all_sessions': all_sessions,
    }
    return render(request, 'telegram_functionality/deleted_messages.html', context)


@login_required
@log_view()
def start_sync(request):
    """Start a new background sync task."""
    logger.info(f"User {request.user.id} initiating background sync")

    session = get_current_session(request.user)
    if not session or not session.is_active:
        logger.warning(f"User {request.user.id} attempted sync with inactive session")
        messages.error(request, 'Telegram session not active')
        return redirect('telegram:connect')

    # Check if there's already a running sync
    running_sync = SyncTask.objects.filter(
        session=session,
        status__in=['pending', 'running']
    ).first()

    if running_sync:
        logger.info(f"User {request.user.id} has existing sync in progress: Task #{running_sync.id}")
        messages.info(request, 'A sync is already in progress.')
        return redirect('telegram:sync_status', task_id=running_sync.id)

    # Create new sync task
    sync_task = SyncTask.objects.create(
        session=session,
        task_type='sync_all',
        status='pending'
    )
    logger.info(f"Created SyncTask #{sync_task.id} for user {request.user.id}")
    log_user_action(request.user, "sync_started", f"Task ID: {sync_task.id}")

    # Start background sync
    start_background_sync(sync_task)
    logger.info(f"Background sync started for Task #{sync_task.id}")

    messages.success(request, 'Sync started! You can continue browsing while syncing.')
    return redirect('telegram:sync_status', task_id=sync_task.id)


@login_required
def sync_status(request, task_id):
    """View sync task status page."""
    session = get_current_session(request.user)
    if not session:
        return redirect('telegram:connect')

    try:
        sync_task = SyncTask.objects.get(id=task_id, session=session)
    except SyncTask.DoesNotExist:
        messages.error(request, 'Sync task not found.')
        return redirect('telegram:dashboard')

    # Get recent sync history
    recent_tasks = SyncTask.objects.filter(
        session=session
    ).exclude(id=task_id).order_by('-created_at')[:5]

    all_sessions = get_all_user_sessions(request.user)

    context = {
        'task': sync_task,
        'recent_tasks': recent_tasks,
        'session': session,
        'all_sessions': all_sessions,
    }
    return render(request, 'telegram_functionality/sync_status.html', context)


@login_required
def sync_progress_api(request, task_id):
    """API endpoint to get sync progress (for AJAX polling)."""
    session = get_current_session(request.user)
    if not session:
        return JsonResponse({'success': False, 'error': 'No session found'})

    try:
        sync_task = SyncTask.objects.get(id=task_id, session=session)
    except SyncTask.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sync task not found'})

    return JsonResponse({
        'success': True,
        'status': sync_task.status,
        'progress_percent': sync_task.progress_percent,
        'total_chats': sync_task.total_chats,
        'synced_chats': sync_task.synced_chats,
        'total_messages': sync_task.total_messages,
        'synced_messages': sync_task.synced_messages,
        'new_messages': sync_task.new_messages,
        'current_chat_title': sync_task.current_chat_title,
        'current_chat_progress': sync_task.current_chat_progress,
        'is_running': sync_task.is_running,
        'is_finished': sync_task.is_finished,
        'error_message': sync_task.error_message,
        'log': sync_task.log,
        'started_at': sync_task.started_at.isoformat() if sync_task.started_at else None,
        'completed_at': sync_task.completed_at.isoformat() if sync_task.completed_at else None,
    })


@login_required
def cancel_sync(request, task_id):
    """Cancel a running sync task."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    session = get_current_session(request.user)
    if not session:
        return JsonResponse({'success': False, 'error': 'No session found'})

    try:
        sync_task = SyncTask.objects.get(id=task_id, session=session)
    except SyncTask.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sync task not found'})

    if sync_task.status in ['pending', 'running']:
        sync_task.status = 'cancelled'
        sync_task.completed_at = timezone.now()
        sync_task.save()
        sync_task.add_log('Sync cancelled by user')

        return JsonResponse({'success': True, 'message': 'Sync cancelled'})
    else:
        return JsonResponse({'success': False, 'error': 'Sync is not running'})


@login_required
def sync_history(request):
    """View all sync task history."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    tasks = SyncTask.objects.filter(session=session).order_by('-created_at')
    all_sessions = get_all_user_sessions(request.user)

    context = {
        'tasks': tasks,
        'session': session,
        'all_sessions': all_sessions,
    }
    return render(request, 'telegram_functionality/sync_history.html', context)


# Session management views


@login_required
def sessions_list(request):
    """View all Telegram sessions for the user."""
    sessions = get_all_user_sessions(request.user)

    context = {
        'sessions': sessions,
        'session_count': sessions.count(),
    }
    return render(request, 'telegram_functionality/sessions.html', context)


@login_required
def switch_session(request, session_id):
    """Switch to a different Telegram session."""
    session = get_object_or_404(TelegramSession, id=session_id, user=request.user)

    if not session.is_active:
        messages.error(request, 'Cannot switch to an inactive session.')
        return redirect('telegram:sessions')

    session.set_as_current()
    messages.success(request, f'Switched to session: {session.get_display_name()}')

    # Redirect to dashboard or wherever the user came from
    next_url = request.GET.get('next', 'telegram:dashboard')
    return redirect(next_url)


@login_required
def update_session(request, session_id):
    """Update session display name."""
    session = get_object_or_404(TelegramSession, id=session_id, user=request.user)

    if request.method == 'POST':
        display_name = request.POST.get('display_name', '').strip()
        if display_name:
            session.display_name = display_name
            session.save(update_fields=['display_name'])
            messages.success(request, 'Session name updated.')
        else:
            session.display_name = None
            session.save(update_fields=['display_name'])
            messages.success(request, 'Session name cleared.')

    return redirect('telegram:sessions')


# Search views


@login_required
def search_messages(request):
    """Advanced search for messages."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    form = AdvancedSearchForm(request.GET or None, session=session)
    results = []
    total_results = 0
    searched = False

    if request.GET and form.is_valid():
        searched = True
        queryset = TelegramMessage.objects.filter(
            chat__session=session
        ).select_related('chat')

        # Text search
        query = form.cleaned_data.get('query')
        if query:
            queryset = queryset.filter(
                Q(text__icontains=query) |
                Q(sender_name__icontains=query)
            )

        # Date filters
        date_from = form.cleaned_data.get('date_from')
        if date_from:
            queryset = queryset.filter(date__date__gte=date_from)

        date_to = form.cleaned_data.get('date_to')
        if date_to:
            queryset = queryset.filter(date__date__lte=date_to)

        # Chat filter
        chat_id = form.cleaned_data.get('chat_id')
        if chat_id:
            queryset = queryset.filter(chat__chat_id=int(chat_id))

        # Chat type filter
        chat_type = form.cleaned_data.get('chat_type')
        if chat_type:
            if chat_type == 'group':
                queryset = queryset.filter(chat__chat_type__in=['group', 'supergroup'])
            else:
                queryset = queryset.filter(chat__chat_type=chat_type)

        # Sender filter
        sender = form.cleaned_data.get('sender')
        if sender:
            queryset = queryset.filter(sender_name__icontains=sender)

        # Direction filter
        direction = form.cleaned_data.get('direction')
        if direction == 'outgoing':
            queryset = queryset.filter(is_outgoing=True)
        elif direction == 'incoming':
            queryset = queryset.filter(is_outgoing=False)

        # Media filter
        media_filter = form.cleaned_data.get('media_filter')
        if media_filter == 'has_media':
            queryset = queryset.filter(has_media=True)
        elif media_filter == 'no_media':
            queryset = queryset.filter(has_media=False)
        elif media_filter == 'photo':
            queryset = queryset.filter(has_media=True, media_mime_type__startswith='image/')
        elif media_filter == 'video':
            queryset = queryset.filter(has_media=True, media_mime_type__startswith='video/')
        elif media_filter == 'document':
            queryset = queryset.filter(has_media=True).exclude(
                Q(media_mime_type__startswith='image/') |
                Q(media_mime_type__startswith='video/') |
                Q(media_mime_type__startswith='audio/')
            )
        elif media_filter == 'audio':
            queryset = queryset.filter(has_media=True, media_mime_type__startswith='audio/')

        # Deleted filter
        deleted_filter = form.cleaned_data.get('deleted_filter')
        if deleted_filter == 'deleted':
            queryset = queryset.filter(is_deleted=True)
        elif deleted_filter == 'not_deleted':
            queryset = queryset.filter(is_deleted=False)

        # Sort
        sort_by = form.cleaned_data.get('sort_by') or '-date'
        queryset = queryset.order_by(sort_by)

        # Pagination
        total_results = queryset.count()
        page = int(request.GET.get('page', 1))
        per_page = 50
        offset = (page - 1) * per_page
        total_pages = (total_results + per_page - 1) // per_page

        results = queryset[offset:offset + per_page]

        context = {
            'form': form,
            'results': results,
            'total_results': total_results,
            'searched': searched,
            'session': session,
            'all_sessions': get_all_user_sessions(request.user),
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
        }
    else:
        context = {
            'form': form,
            'results': [],
            'total_results': 0,
            'searched': False,
            'session': session,
            'all_sessions': get_all_user_sessions(request.user),
        }

    return render(request, 'telegram_functionality/search.html', context)


@login_required
def search_chats(request):
    """Search chats by name."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    query = request.GET.get('q', '').strip()
    chat_type = request.GET.get('type', '')

    chats = TelegramChat.objects.filter(session=session)

    if query:
        chats = chats.filter(
            Q(title__icontains=query) |
            Q(username__icontains=query)
        )

    if chat_type:
        if chat_type == 'groups':
            chats = chats.filter(chat_type__in=['group', 'supergroup'])
        elif chat_type == 'channels':
            chats = chats.filter(chat_type='channel')
        elif chat_type == 'users':
            chats = chats.filter(chat_type='user')

    chats = chats.order_by('title')

    # Build chat list with stats
    chat_list = []
    for chat in chats:
        last_message = chat.messages.first()
        chat_list.append({
            'id': chat.chat_id,
            'title': chat.title,
            'type': chat.chat_type,
            'username': chat.username,
            'members_count': chat.members_count,
            'total_messages': chat.total_messages,
            'last_message': {
                'text': last_message.text[:100] if last_message else '',
                'date': last_message.date if last_message else None,
            } if last_message else None,
        })

    context = {
        'chats': chat_list,
        'query': query,
        'chat_type': chat_type,
        'total': len(chat_list),
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/search_chats.html', context)


# Media download views

@login_required
def trigger_media_download(request, message_id):
    """Trigger manual download of a single message's media."""
    message = get_object_or_404(TelegramMessage, id=message_id)

    # Security check: ensure user owns this message
    if message.chat.session.user != request.user:
        return JsonResponse({'success': False, 'error': 'Access denied'}, status=403)

    if not message.has_media:
        return JsonResponse({'success': False, 'error': 'Message has no media'})

    if message.media_file:
        return JsonResponse({'success': False, 'error': 'Media already downloaded'})

    session = message.chat.session
    if not session.is_active:
        return JsonResponse({'success': False, 'error': 'Telegram session is not active'})

    try:
        session_string = session.get_session_string()
        result = telegram_manager.download_single_media(
            session_string=session_string,
            chat_id=message.chat.chat_id,
            message_id=message.message_id,
            save_dir=settings.MEDIA_ROOT,
            user_id=request.user.id
        )

        if result['success']:
            # Update the message with downloaded file info
            message.media_file = result['file_path']
            message.media_file_name = result.get('file_name')
            message.media_file_size = result.get('file_size')
            message.media_mime_type = result.get('mime_type')
            message.save()

            return JsonResponse({
                'success': True,
                'file_name': result.get('file_name'),
                'file_size': result.get('file_size'),
            })
        else:
            return JsonResponse({'success': False, 'error': result.get('error', 'Download failed')})

    except Exception as e:
        logger.error(f"Error triggering media download: {e}")
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def pending_downloads_api(request):
    """API endpoint to get count and size of pending media downloads."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return JsonResponse({'success': False, 'error': 'No active session'})

    # Get messages with media but no downloaded file
    pending = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True,
    ).filter(
        Q(media_file='') | Q(media_file__isnull=True)
    )

    # Count and calculate total size
    total_count = pending.count()

    # Sum up known file sizes
    total_size = 0
    size_unknown_count = 0

    for msg in pending.values('media_file_size'):
        if msg['media_file_size']:
            total_size += msg['media_file_size']
        else:
            size_unknown_count += 1

    return JsonResponse({
        'success': True,
        'total_count': total_count,
        'total_size': total_size,
        'size_unknown_count': size_unknown_count,
        'total_size_formatted': f"{total_size / (1024 * 1024):.2f} MB" if total_size else "Unknown"
    })


@login_required
def bulk_download_media(request):
    """View page for bulk downloading pending media."""
    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return redirect_response

    # Get pending downloads
    pending = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True,
    ).filter(
        Q(media_file='') | Q(media_file__isnull=True)
    ).select_related('chat')

    total_count = pending.count()

    # Calculate sizes by chat
    chats_with_pending = {}
    total_size = 0

    for msg in pending:
        chat_id = msg.chat.chat_id
        if chat_id not in chats_with_pending:
            chats_with_pending[chat_id] = {
                'chat': msg.chat,
                'count': 0,
                'size': 0,
            }
        chats_with_pending[chat_id]['count'] += 1
        if msg.media_file_size:
            chats_with_pending[chat_id]['size'] += msg.media_file_size
            total_size += msg.media_file_size

    context = {
        'total_count': total_count,
        'total_size': total_size,
        'total_size_mb': total_size / (1024 * 1024) if total_size else 0,
        'chats_with_pending': list(chats_with_pending.values()),
        'session': session,
        'all_sessions': get_all_user_sessions(request.user),
    }

    return render(request, 'telegram_functionality/bulk_download.html', context)


@login_required
def start_bulk_download(request):
    """Start bulk download of pending media files."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    session, redirect_response = get_session_or_redirect(request)
    if redirect_response:
        return JsonResponse({'success': False, 'error': 'No active session'})

    # Get pending downloads
    pending = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True,
    ).filter(
        Q(media_file='') | Q(media_file__isnull=True)
    ).select_related('chat')[:100]  # Limit batch size

    if not pending:
        return JsonResponse({'success': True, 'downloaded': 0, 'message': 'No pending downloads'})

    downloaded = 0
    failed = 0
    session_string = session.get_session_string()

    for message in pending:
        try:
            result = telegram_manager.download_single_media(
                session_string=session_string,
                chat_id=message.chat.chat_id,
                message_id=message.message_id,
                save_dir=settings.MEDIA_ROOT,
                user_id=request.user.id
            )

            if result['success']:
                message.media_file = result['file_path']
                message.media_file_name = result.get('file_name')
                message.media_file_size = result.get('file_size')
                message.media_mime_type = result.get('mime_type')
                message.save()
                downloaded += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Error downloading media for message {message.id}: {e}")
            failed += 1

    # Check remaining
    remaining = TelegramMessage.objects.filter(
        chat__session=session,
        has_media=True,
    ).filter(
        Q(media_file='') | Q(media_file__isnull=True)
    ).count()

    return JsonResponse({
        'success': True,
        'downloaded': downloaded,
        'failed': failed,
        'remaining': remaining,
    })
