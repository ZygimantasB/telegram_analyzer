from django import forms
from .models import TelegramChat


class PhoneNumberForm(forms.Form):
    """Form for entering phone number."""
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '+1234567890',
            'autofocus': True,
        }),
        help_text='Enter your phone number with country code (e.g., +1234567890)'
    )

    def clean_phone_number(self):
        phone = self.cleaned_data['phone_number']
        # Remove spaces and dashes
        phone = phone.replace(' ', '').replace('-', '')
        # Ensure it starts with +
        if not phone.startswith('+'):
            phone = '+' + phone
        return phone


class VerificationCodeForm(forms.Form):
    """Form for entering verification code."""
    code = forms.CharField(
        max_length=10,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg text-center',
            'placeholder': '12345',
            'autofocus': True,
            'autocomplete': 'one-time-code',
        }),
        help_text='Enter the code sent to your Telegram app'
    )

    def clean_code(self):
        code = self.cleaned_data['code']
        # Remove any spaces
        return code.replace(' ', '')


class TwoFactorForm(forms.Form):
    """Form for entering 2FA password."""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Your 2FA password',
            'autofocus': True,
        }),
        help_text='Enter your Telegram two-factor authentication password'
    )


class AdvancedSearchForm(forms.Form):
    """Advanced search form for messages."""

    # Text search
    query = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search messages...',
        }),
        label='Keywords'
    )

    # Date range
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label='From Date'
    )

    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
        }),
        label='To Date'
    )

    # Chat filter (will be populated dynamically)
    chat_id = forms.ChoiceField(
        required=False,
        choices=[('', 'All Chats')],
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label='Chat'
    )

    # Chat type filter
    CHAT_TYPE_CHOICES = [
        ('', 'All Types'),
        ('user', 'Private Chats'),
        ('group', 'Groups'),
        ('supergroup', 'Supergroups'),
        ('channel', 'Channels'),
    ]
    chat_type = forms.ChoiceField(
        required=False,
        choices=CHAT_TYPE_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label='Chat Type'
    )

    # Sender filter
    sender = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Sender name...',
        }),
        label='From (Sender)'
    )

    # Message direction
    DIRECTION_CHOICES = [
        ('', 'All Messages'),
        ('outgoing', 'Sent by me'),
        ('incoming', 'Received'),
    ]
    direction = forms.ChoiceField(
        required=False,
        choices=DIRECTION_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label='Direction'
    )

    # Media filter
    MEDIA_CHOICES = [
        ('', 'All Messages'),
        ('has_media', 'With Media'),
        ('no_media', 'Text Only'),
        ('photo', 'Photos'),
        ('video', 'Videos'),
        ('document', 'Documents'),
        ('audio', 'Audio'),
    ]
    media_filter = forms.ChoiceField(
        required=False,
        choices=MEDIA_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label='Media'
    )

    # Deleted messages filter
    DELETED_CHOICES = [
        ('', 'All Messages'),
        ('deleted', 'Deleted Only'),
        ('not_deleted', 'Active Only'),
    ]
    deleted_filter = forms.ChoiceField(
        required=False,
        choices=DELETED_CHOICES,
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label='Status'
    )

    # Sort options
    SORT_CHOICES = [
        ('-date', 'Newest First'),
        ('date', 'Oldest First'),
        ('-deleted_at', 'Recently Deleted'),
        ('sender_name', 'Sender A-Z'),
        ('-sender_name', 'Sender Z-A'),
    ]
    sort_by = forms.ChoiceField(
        required=False,
        choices=SORT_CHOICES,
        initial='-date',
        widget=forms.Select(attrs={
            'class': 'form-select',
        }),
        label='Sort By'
    )

    def __init__(self, *args, session=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate chat choices from session
        if session:
            chats = TelegramChat.objects.filter(session=session).order_by('title')
            chat_choices = [('', 'All Chats')]
            chat_choices += [(str(chat.chat_id), chat.title) for chat in chats]
            self.fields['chat_id'].choices = chat_choices
