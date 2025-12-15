from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.db.models import Q

from .forms import PhoneNumberForm, VerificationCodeForm, TwoFactorForm
from .models import TelegramSession, TelegramChat, TelegramMessage, SyncTask
from .services import telegram_manager, start_background_sync


@login_required
def telegram_connect(request):
    """View to start Telegram connection process."""
    # Check if user already has an active session
    try:
        session = request.user.telegram_session
        if session.is_active:
            return redirect('telegram:dashboard')
    except TelegramSession.DoesNotExist:
        pass

    if request.method == 'POST':
        form = PhoneNumberForm(request.POST)
        if form.is_valid():
            phone_number = form.cleaned_data['phone_number']

            # Send verification code
            result = telegram_manager.send_code(phone_number)

            if result['success']:
                # Store data in session for next step
                request.session['telegram_phone'] = phone_number
                request.session['telegram_phone_code_hash'] = result['phone_code_hash']
                request.session['telegram_session_string'] = result['session_string']
                return redirect('telegram:verify_code')
            else:
                messages.error(request, result.get('error', 'Failed to send code'))
    else:
        form = PhoneNumberForm()

    return render(request, 'telegram_functionality/connect.html', {'form': form})


@login_required
def verify_code(request):
    """View to verify the code sent to phone."""
    # Check if we have the required session data
    if 'telegram_phone' not in request.session:
        messages.error(request, 'Please enter your phone number first.')
        return redirect('telegram:connect')

    phone_number = request.session['telegram_phone']

    if request.method == 'POST':
        form = VerificationCodeForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['code']

            result = telegram_manager.verify_code(
                session_string=request.session['telegram_session_string'],
                phone_number=phone_number,
                phone_code_hash=request.session['telegram_phone_code_hash'],
                code=code
            )

            if result['success']:
                if result.get('requires_2fa'):
                    # User has 2FA enabled
                    request.session['telegram_session_string'] = result['session_string']
                    return redirect('telegram:verify_2fa')
                else:
                    # Successfully logged in
                    _save_telegram_session(request, result)
                    _clear_telegram_session_data(request)
                    messages.success(request, 'Successfully connected to Telegram!')
                    return redirect('telegram:dashboard')
            else:
                messages.error(request, result.get('error', 'Verification failed'))
    else:
        form = VerificationCodeForm()

    return render(request, 'telegram_functionality/verify_code.html', {
        'form': form,
        'phone_number': phone_number,
    })


@login_required
def verify_2fa(request):
    """View to verify 2FA password."""
    if 'telegram_session_string' not in request.session:
        messages.error(request, 'Please start the connection process again.')
        return redirect('telegram:connect')

    if request.method == 'POST':
        form = TwoFactorForm(request.POST)
        if form.is_valid():
            password = form.cleaned_data['password']

            result = telegram_manager.verify_2fa(
                session_string=request.session['telegram_session_string'],
                password=password
            )

            if result['success']:
                _save_telegram_session(request, result)
                _clear_telegram_session_data(request)
                messages.success(request, 'Successfully connected to Telegram!')
                return redirect('telegram:dashboard')
            else:
                messages.error(request, result.get('error', '2FA verification failed'))
    else:
        form = TwoFactorForm()

    return render(request, 'telegram_functionality/verify_2fa.html', {'form': form})


@login_required
def telegram_dashboard(request):
    """Dashboard showing Telegram connection status and chats."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

        chats = session.chats.all()[:20]

        # Calculate stats
        stats = {
            'users': session.chats.filter(chat_type='user').count(),
            'groups': session.chats.filter(chat_type__in=['group', 'supergroup']).count(),
            'channels': session.chats.filter(chat_type='channel').count(),
        }

        context = {
            'session': session,
            'chats': chats,
            'stats': stats,
        }
        return render(request, 'telegram_functionality/dashboard.html', context)
    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')


@login_required
def telegram_disconnect(request):
    """Disconnect Telegram session."""
    if request.method == 'POST':
        try:
            session = request.user.telegram_session
            session_string = session.get_session_string()

            if session_string:
                telegram_manager.disconnect_session(session_string)

            session.delete()
            messages.success(request, 'Telegram disconnected successfully.')
        except TelegramSession.DoesNotExist:
            messages.info(request, 'No Telegram session found.')

    return redirect('telegram:connect')


@login_required
def sync_chats(request):
    """Sync user's Telegram chats."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return JsonResponse({'success': False, 'error': 'Session not active'})

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

    except TelegramSession.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'No session found'})
        messages.error(request, 'No Telegram session found.')

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
    """Save Telegram session to database."""
    session, created = TelegramSession.objects.update_or_create(
        user=request.user,
        defaults={
            'phone_number': request.session.get('telegram_phone', ''),
            'telegram_user_id': result.get('user_id'),
            'telegram_username': result.get('username'),
            'telegram_first_name': result.get('first_name'),
            'telegram_last_name': result.get('last_name'),
            'is_active': True,
        }
    )
    session.set_session_string(result['session_string'])
    session.save()


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
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

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

        context = {
            'chats': chat_list,
            'total': total,
            'current_filter': chat_type,
            'session': session,
            'needs_sync': total == 0,
        }
        return render(request, 'telegram_functionality/chat_list.html', context)

    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')


@login_required
def chat_messages(request, chat_id):
    """View messages from database for a specific chat."""
    chat_id = int(chat_id)  # Convert from string (re_path passes as string)
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

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
            'last_synced': chat.last_synced,
        }
        return render(request, 'telegram_functionality/chat_messages.html', context)

    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')


@login_required
def load_more_messages(request, chat_id):
    """Load more messages (AJAX endpoint)."""
    chat_id = int(chat_id)  # Convert from string (re_path passes as string)
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return JsonResponse({'success': False, 'error': 'Session not active'})

        session_string = session.get_session_string()
        offset_id = int(request.GET.get('offset_id', 0))
        limit = int(request.GET.get('limit', 50))

        result = telegram_manager.get_messages(session_string, chat_id, limit=limit, offset_id=offset_id)
        return JsonResponse(result)

    except TelegramSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No session found'})


@login_required
def all_messages(request):
    """View all messages from database."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

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
        }
        return render(request, 'telegram_functionality/all_messages.html', context)

    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')


@login_required
def sync_all_chats(request):
    """Sync all chats and their messages to database."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return JsonResponse({'success': False, 'error': 'Session not active'})

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

    except TelegramSession.DoesNotExist:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'error': 'No session found'})
        return redirect('telegram:connect')


@login_required
def sync_chat_messages(request, chat_id):
    """Sync messages for a specific chat."""
    chat_id = int(chat_id)
    try:
        session = request.user.telegram_session
        if not session.is_active:
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

    except TelegramSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No session found'})


@login_required
def check_deleted_messages(request, chat_id=None):
    """Check for deleted messages by comparing DB with Telegram API."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
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

    except TelegramSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No session found'})


@login_required
def deleted_messages(request):
    """View all deleted messages."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

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

        context = {
            'deleted_messages': deleted_msgs,
            'chats_with_deleted': chats_with_deleted,
            'selected_chat_id': chat_id,
            'total_deleted': deleted_msgs.count(),
            'session': session,
        }
        return render(request, 'telegram_functionality/deleted_messages.html', context)

    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')


@login_required
def start_sync(request):
    """Start a new background sync task."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            messages.error(request, 'Telegram session not active')
            return redirect('telegram:connect')

        # Check if there's already a running sync
        running_sync = SyncTask.objects.filter(
            session=session,
            status__in=['pending', 'running']
        ).first()

        if running_sync:
            messages.info(request, 'A sync is already in progress.')
            return redirect('telegram:sync_status', task_id=running_sync.id)

        # Create new sync task
        sync_task = SyncTask.objects.create(
            session=session,
            task_type='sync_all',
            status='pending'
        )

        # Start background sync
        start_background_sync(sync_task)

        messages.success(request, 'Sync started! You can continue browsing while syncing.')
        return redirect('telegram:sync_status', task_id=sync_task.id)

    except TelegramSession.DoesNotExist:
        messages.error(request, 'No Telegram session found.')
        return redirect('telegram:connect')


@login_required
def sync_status(request, task_id):
    """View sync task status page."""
    try:
        session = request.user.telegram_session
        sync_task = SyncTask.objects.get(id=task_id, session=session)

        # Get recent sync history
        recent_tasks = SyncTask.objects.filter(
            session=session
        ).exclude(id=task_id).order_by('-created_at')[:5]

        context = {
            'task': sync_task,
            'recent_tasks': recent_tasks,
            'session': session,
        }
        return render(request, 'telegram_functionality/sync_status.html', context)

    except SyncTask.DoesNotExist:
        messages.error(request, 'Sync task not found.')
        return redirect('telegram:dashboard')
    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')


@login_required
def sync_progress_api(request, task_id):
    """API endpoint to get sync progress (for AJAX polling)."""
    try:
        session = request.user.telegram_session
        sync_task = SyncTask.objects.get(id=task_id, session=session)

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

    except SyncTask.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sync task not found'})
    except TelegramSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No session found'})


@login_required
def cancel_sync(request, task_id):
    """Cancel a running sync task."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'})

    try:
        session = request.user.telegram_session
        sync_task = SyncTask.objects.get(id=task_id, session=session)

        if sync_task.status in ['pending', 'running']:
            sync_task.status = 'cancelled'
            sync_task.completed_at = timezone.now()
            sync_task.save()
            sync_task.add_log('Sync cancelled by user')

            return JsonResponse({'success': True, 'message': 'Sync cancelled'})
        else:
            return JsonResponse({'success': False, 'error': 'Sync is not running'})

    except SyncTask.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Sync task not found'})
    except TelegramSession.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'No session found'})


@login_required
def sync_history(request):
    """View all sync task history."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

        tasks = SyncTask.objects.filter(session=session).order_by('-created_at')

        context = {
            'tasks': tasks,
            'session': session,
        }
        return render(request, 'telegram_functionality/sync_history.html', context)

    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')
