"""
Logging utilities for Telegram Analyzer project.

This module provides:
- Pre-configured loggers for different parts of the application
- Decorators for automatic function logging
- Context managers for operation tracking
- Helper functions for structured logging
"""

import logging
import functools
import time
import traceback
from contextlib import contextmanager
from typing import Optional, Any, Callable
from django.http import HttpRequest


# =============================================================================
# PRE-CONFIGURED LOGGERS
# =============================================================================

def get_logger(name: str) -> logging.Logger:
    """Get a logger with the specified name."""
    return logging.getLogger(name)


# App-specific loggers
telegram_logger = get_logger('telegram_functionality')
telegram_views_logger = get_logger('telegram_functionality.views')
telegram_services_logger = get_logger('telegram_functionality.services')
telegram_sync_logger = get_logger('telegram_functionality.sync')
users_logger = get_logger('users')
users_views_logger = get_logger('users.views')
security_logger = get_logger('security')


# =============================================================================
# LOGGING DECORATORS
# =============================================================================

def log_function_call(logger: Optional[logging.Logger] = None, level: int = logging.DEBUG):
    """
    Decorator to log function entry, exit, and exceptions.

    Usage:
        @log_function_call()
        def my_function():
            pass

        @log_function_call(telegram_logger, logging.INFO)
        def my_important_function():
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_logger = logger or logging.getLogger(func.__module__)
            func_name = func.__qualname__

            # Log entry
            func_logger.log(level, f"ENTER: {func_name}() - args: {len(args)}, kwargs: {list(kwargs.keys())}")

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time
                func_logger.log(level, f"EXIT: {func_name}() - completed in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.time() - start_time
                func_logger.error(
                    f"ERROR: {func_name}() - {type(e).__name__}: {str(e)} (after {elapsed:.3f}s)"
                )
                func_logger.debug(f"Traceback for {func_name}():\n{traceback.format_exc()}")
                raise
        return wrapper
    return decorator


def log_view(logger: Optional[logging.Logger] = None):
    """
    Decorator specifically for Django views.
    Logs request method, path, user, and response status.

    Usage:
        @log_view()
        def my_view(request):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            view_logger = logger or telegram_views_logger
            view_name = func.__qualname__
            user = request.user if hasattr(request, 'user') else 'Anonymous'
            user_id = getattr(user, 'id', None) if hasattr(user, 'id') else None

            # Log request
            view_logger.info(
                f"VIEW REQUEST: {view_name} | {request.method} {request.path} | "
                f"User: {user} (ID: {user_id})"
            )

            start_time = time.time()
            try:
                response = func(request, *args, **kwargs)
                elapsed = time.time() - start_time

                status_code = getattr(response, 'status_code', 'N/A')
                view_logger.info(
                    f"VIEW RESPONSE: {view_name} | Status: {status_code} | "
                    f"Time: {elapsed:.3f}s"
                )
                return response
            except Exception as e:
                elapsed = time.time() - start_time
                view_logger.error(
                    f"VIEW ERROR: {view_name} | {type(e).__name__}: {str(e)} | "
                    f"Time: {elapsed:.3f}s"
                )
                raise
        return wrapper
    return decorator


def log_api_call(logger: Optional[logging.Logger] = None):
    """
    Decorator for Telegram API calls.
    Logs API operation details and timing.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            api_logger = logger or telegram_services_logger
            func_name = func.__qualname__

            api_logger.info(f"API CALL START: {func_name}")

            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start_time

                # Log success/failure based on result
                if isinstance(result, dict):
                    success = result.get('success', True)
                    if success:
                        api_logger.info(f"API CALL SUCCESS: {func_name} - {elapsed:.3f}s")
                    else:
                        error = result.get('error', 'Unknown error')
                        api_logger.warning(f"API CALL FAILED: {func_name} - {error} - {elapsed:.3f}s")
                else:
                    api_logger.info(f"API CALL COMPLETE: {func_name} - {elapsed:.3f}s")

                return result
            except Exception as e:
                elapsed = time.time() - start_time
                api_logger.error(f"API CALL EXCEPTION: {func_name} - {type(e).__name__}: {str(e)} - {elapsed:.3f}s")
                api_logger.debug(f"Traceback:\n{traceback.format_exc()}")
                raise
        return wrapper
    return decorator


# =============================================================================
# CONTEXT MANAGERS
# =============================================================================

@contextmanager
def log_operation(operation_name: str, logger: Optional[logging.Logger] = None, level: int = logging.INFO):
    """
    Context manager for logging operations.

    Usage:
        with log_operation("Processing messages", telegram_sync_logger):
            # do work
            pass
    """
    op_logger = logger or telegram_logger
    op_logger.log(level, f"OPERATION START: {operation_name}")
    start_time = time.time()

    try:
        yield
        elapsed = time.time() - start_time
        op_logger.log(level, f"OPERATION COMPLETE: {operation_name} - {elapsed:.3f}s")
    except Exception as e:
        elapsed = time.time() - start_time
        op_logger.error(f"OPERATION FAILED: {operation_name} - {type(e).__name__}: {str(e)} - {elapsed:.3f}s")
        raise


@contextmanager
def log_sync_operation(chat_title: str, operation: str = "sync"):
    """
    Context manager specifically for sync operations.

    Usage:
        with log_sync_operation("My Chat", "message_sync"):
            # sync messages
            pass
    """
    telegram_sync_logger.info(f"SYNC START: {operation} for '{chat_title}'")
    start_time = time.time()

    try:
        yield
        elapsed = time.time() - start_time
        telegram_sync_logger.info(f"SYNC COMPLETE: {operation} for '{chat_title}' - {elapsed:.3f}s")
    except Exception as e:
        elapsed = time.time() - start_time
        telegram_sync_logger.error(
            f"SYNC FAILED: {operation} for '{chat_title}' - {type(e).__name__}: {str(e)} - {elapsed:.3f}s"
        )
        raise


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def log_user_action(user, action: str, details: Optional[str] = None):
    """
    Log a user action for audit purposes.

    Usage:
        log_user_action(request.user, "login", "from IP 192.168.1.1")
    """
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', str(user))
    email = getattr(user, 'email', 'N/A')

    message = f"USER ACTION: {action} | User: {username} (ID: {user_id}, Email: {email})"
    if details:
        message += f" | Details: {details}"

    security_logger.info(message)


def log_security_event(event_type: str, user=None, ip_address: Optional[str] = None, details: Optional[str] = None):
    """
    Log security-related events.

    Usage:
        log_security_event("failed_login", ip_address="192.168.1.1", details="Invalid password")
    """
    message = f"SECURITY EVENT: {event_type}"

    if user:
        user_id = getattr(user, 'id', None)
        username = getattr(user, 'username', str(user))
        message += f" | User: {username} (ID: {user_id})"

    if ip_address:
        message += f" | IP: {ip_address}"

    if details:
        message += f" | Details: {details}"

    security_logger.warning(message)


def log_telegram_connection(user, phone_number: str, status: str, details: Optional[str] = None):
    """
    Log Telegram connection events.
    """
    user_id = getattr(user, 'id', None)
    username = getattr(user, 'username', str(user))

    # Mask phone number for security
    masked_phone = phone_number[:4] + "****" + phone_number[-2:] if len(phone_number) > 6 else "****"

    message = f"TELEGRAM CONNECTION: {status} | User: {username} (ID: {user_id}) | Phone: {masked_phone}"
    if details:
        message += f" | Details: {details}"

    telegram_logger.info(message)
    security_logger.info(message)


def log_sync_progress(task_id: int, chats_done: int, total_chats: int, messages_synced: int):
    """
    Log sync progress updates.
    """
    progress = (chats_done / total_chats * 100) if total_chats > 0 else 0
    telegram_sync_logger.info(
        f"SYNC PROGRESS: Task #{task_id} | {chats_done}/{total_chats} chats ({progress:.1f}%) | "
        f"{messages_synced} messages synced"
    )


def log_database_operation(operation: str, model: str, count: int = 1, details: Optional[str] = None):
    """
    Log database operations.
    """
    message = f"DB OPERATION: {operation} | Model: {model} | Count: {count}"
    if details:
        message += f" | Details: {details}"

    telegram_logger.debug(message)


def log_error_with_context(logger: logging.Logger, error: Exception, context: dict):
    """
    Log an error with additional context information.

    Usage:
        log_error_with_context(telegram_logger, e, {
            'user_id': 123,
            'chat_id': -100123456,
            'operation': 'sync_messages'
        })
    """
    context_str = " | ".join(f"{k}={v}" for k, v in context.items())
    logger.error(f"ERROR: {type(error).__name__}: {str(error)} | Context: {context_str}")
    logger.debug(f"Full traceback:\n{traceback.format_exc()}")


def get_client_ip(request: HttpRequest) -> str:
    """Extract client IP address from request."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', 'unknown')
    return ip


# =============================================================================
# PERFORMANCE LOGGING
# =============================================================================

class PerformanceLogger:
    """
    Class for detailed performance logging.

    Usage:
        perf = PerformanceLogger("sync_operation", telegram_sync_logger)
        perf.checkpoint("fetched_chats")
        perf.checkpoint("processed_messages")
        perf.finish()
    """

    def __init__(self, operation_name: str, logger: Optional[logging.Logger] = None):
        self.operation_name = operation_name
        self.logger = logger or telegram_logger
        self.start_time = time.time()
        self.checkpoints = []
        self.logger.info(f"PERF START: {operation_name}")

    def checkpoint(self, name: str, details: Optional[str] = None):
        """Record a checkpoint."""
        elapsed = time.time() - self.start_time
        self.checkpoints.append((name, elapsed))
        message = f"PERF CHECKPOINT: {self.operation_name} | {name} | {elapsed:.3f}s"
        if details:
            message += f" | {details}"
        self.logger.debug(message)

    def finish(self, details: Optional[str] = None):
        """Finish and log summary."""
        total_time = time.time() - self.start_time
        checkpoint_summary = ", ".join(f"{name}: {time:.3f}s" for name, time in self.checkpoints)

        message = f"PERF COMPLETE: {self.operation_name} | Total: {total_time:.3f}s"
        if checkpoint_summary:
            message += f" | Checkpoints: [{checkpoint_summary}]"
        if details:
            message += f" | {details}"

        self.logger.info(message)
        return total_time
