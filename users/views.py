from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.contrib import messages
from django.urls import reverse_lazy
from django.views.generic import CreateView, UpdateView

from .forms import UserRegisterForm, UserLoginForm, UserUpdateForm

# Logging imports
from telegram_analyzer_app.logging_utils import (
    users_views_logger as logger,
    security_logger,
    log_user_action,
    log_security_event,
    get_client_ip,
)


class UserRegisterView(CreateView):
    """View for user registration."""
    form_class = UserRegisterForm
    template_name = 'users/register.html'
    success_url = reverse_lazy('users:login')

    def dispatch(self, request, *args, **kwargs):
        logger.debug(f"UserRegisterView dispatch - authenticated: {request.user.is_authenticated}")
        if request.user.is_authenticated:
            logger.info(f"Authenticated user {request.user.id} redirected from register to profile")
            return redirect('users:profile')
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object
        ip_address = get_client_ip(self.request)
        logger.info(f"New user registered: {user.username} (ID: {user.id}) from IP: {ip_address}")
        log_security_event("user_registered", user, ip_address, f"Email: {user.email}")
        log_user_action(user, "account_created", f"IP: {ip_address}")
        messages.success(self.request, 'Account created successfully! Please log in.')
        return response

    def form_invalid(self, form):
        ip_address = get_client_ip(self.request)
        logger.warning(f"Registration failed from IP: {ip_address} - Errors: {form.errors}")
        return super().form_invalid(form)


class UserLoginView(LoginView):
    """View for user login."""
    form_class = UserLoginForm
    template_name = 'users/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return reverse_lazy('users:profile')

    def form_valid(self, form):
        user = form.get_user()
        ip_address = get_client_ip(self.request)
        logger.info(f"User logged in: {user.username} (ID: {user.id}) from IP: {ip_address}")
        log_security_event("user_login_success", user, ip_address)
        log_user_action(user, "login", f"IP: {ip_address}")
        messages.success(self.request, f'Welcome back, {user.username}!')
        return super().form_valid(form)

    def form_invalid(self, form):
        ip_address = get_client_ip(self.request)
        username = form.data.get('username', 'unknown')
        logger.warning(f"Failed login attempt for '{username}' from IP: {ip_address}")
        log_security_event("user_login_failed", None, ip_address, f"Username: {username}")
        return super().form_invalid(form)


class UserLogoutView(LogoutView):
    """View for user logout."""
    next_page = reverse_lazy('users:login')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            user = request.user
            ip_address = get_client_ip(request)
            logger.info(f"User logged out: {user.username} (ID: {user.id}) from IP: {ip_address}")
            log_security_event("user_logout", user, ip_address)
            log_user_action(user, "logout", f"IP: {ip_address}")
            messages.info(request, 'You have been logged out.')
        return super().dispatch(request, *args, **kwargs)


@login_required
def profile_view(request):
    """View for user profile."""
    logger.debug(f"profile_view called by user {request.user.id}")

    if request.method == 'POST':
        form = UserUpdateForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            logger.info(f"User {request.user.id} updated their profile")
            log_user_action(request.user, "profile_updated", f"Fields: {list(form.changed_data)}")
            messages.success(request, 'Profile updated successfully!')
            return redirect('users:profile')
        else:
            logger.warning(f"Profile update failed for user {request.user.id}: {form.errors}")
    else:
        form = UserUpdateForm(instance=request.user)

    return render(request, 'users/profile.html', {'form': form})


@login_required
def delete_account_view(request):
    """View for deleting user account."""
    logger.debug(f"delete_account_view called by user {request.user.id}")

    if request.method == 'POST':
        user = request.user
        user_id = user.id
        username = user.username
        email = user.email
        ip_address = get_client_ip(request)

        logger.warning(f"User {user_id} ({username}) deleting their account from IP: {ip_address}")
        log_security_event("account_deleted", user, ip_address, f"Email: {email}")

        logout(request)
        user.delete()

        logger.info(f"Account deleted: User ID {user_id} ({username})")
        messages.success(request, 'Your account has been deleted.')
        return redirect('users:login')

    return render(request, 'users/delete_account.html')
