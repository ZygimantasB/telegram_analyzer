from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse

from .forms import PhoneNumberForm, VerificationCodeForm, TwoFactorForm
from .models import TelegramSession
from .services import telegram_manager


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
    """View all chats from Telegram (live fetch)."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

        session_string = session.get_session_string()
        result = telegram_manager.get_all_chats(session_string)

        if result['success']:
            # Filter by type if requested
            chat_type = request.GET.get('type', 'all')
            chats = result['chats']

            if chat_type != 'all':
                if chat_type == 'groups':
                    chats = [c for c in chats if c['type'] in ['group', 'supergroup']]
                elif chat_type == 'channels':
                    chats = [c for c in chats if c['type'] == 'channel']
                elif chat_type == 'users':
                    chats = [c for c in chats if c['type'] == 'user']

            context = {
                'chats': chats,
                'total': result['total'],
                'current_filter': chat_type,
                'session': session,
            }
            return render(request, 'telegram_functionality/chat_list.html', context)
        else:
            messages.error(request, result.get('error', 'Failed to fetch chats'))
            return redirect('telegram:dashboard')

    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')


@login_required
def chat_messages(request, chat_id):
    """View messages from a specific chat."""
    chat_id = int(chat_id)  # Convert from string (re_path passes as string)
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

        session_string = session.get_session_string()

        # Get chat info
        chat_result = telegram_manager.get_chat_info(session_string, chat_id)
        if not chat_result['success']:
            messages.error(request, chat_result.get('error', 'Failed to get chat info'))
            return redirect('telegram:chats')

        # Get messages
        limit = int(request.GET.get('limit', 50))
        offset_id = int(request.GET.get('offset_id', 0))

        msg_result = telegram_manager.get_messages(session_string, chat_id, limit=limit, offset_id=offset_id)

        if msg_result['success']:
            context = {
                'chat': chat_result['chat'],
                'messages': msg_result['messages'],
                'chat_id': chat_id,
                'limit': limit,
                'session': session,
            }
            return render(request, 'telegram_functionality/chat_messages.html', context)
        else:
            messages.error(request, msg_result.get('error', 'Failed to fetch messages'))
            return redirect('telegram:chats')

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
    """View all messages from all chats combined."""
    try:
        session = request.user.telegram_session
        if not session.is_active:
            return redirect('telegram:connect')

        session_string = session.get_session_string()

        # Get parameters
        limit_per_chat = int(request.GET.get('limit', 5))
        max_chats = int(request.GET.get('chats', 30))

        result = telegram_manager.get_all_messages(
            session_string,
            limit_per_chat=limit_per_chat,
            max_chats=max_chats
        )

        if result['success']:
            context = {
                'telegram_messages': result['messages'],
                'total': result['total'],
                'limit_per_chat': limit_per_chat,
                'max_chats': max_chats,
                'session': session,
            }
            return render(request, 'telegram_functionality/all_messages.html', context)
        else:
            messages.error(request, result.get('error', 'Failed to fetch messages'))
            return redirect('telegram:dashboard')

    except TelegramSession.DoesNotExist:
        return redirect('telegram:connect')
