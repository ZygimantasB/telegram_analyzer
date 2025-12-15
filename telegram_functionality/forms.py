from django import forms


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
