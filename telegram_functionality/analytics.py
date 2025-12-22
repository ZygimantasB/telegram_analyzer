"""
Analytics module for computing statistics and insights from Telegram data.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from django.db.models import Count, Sum, Q, F
from django.db.models.functions import TruncDate, TruncHour, ExtractHour, ExtractWeekDay
from django.utils import timezone

from .models import TelegramMessage, TelegramChat, TelegramSession, AnalyticsCache


class AnalyticsService:
    """Service for computing analytics and statistics."""

    # Common stop words to exclude from word frequency
    STOP_WORDS = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
        'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how', 'all',
        'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
        'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very',
        'just', 'also', 'now', 'here', 'there', 'then', 'if', 'else', 'as',
        'до', 'на', 'в', 'и', 'с', 'по', 'у', 'за', 'из', 'о', 'от', 'к', 'не',
        'что', 'это', 'как', 'так', 'все', 'он', 'она', 'они', 'мы', 'вы', 'я',
    }

    def __init__(self, session: TelegramSession):
        self.session = session

    def get_messages_queryset(self, chat_id=None, date_from=None, date_to=None):
        """Get base messages queryset with optional filters."""
        qs = TelegramMessage.objects.filter(chat__session=self.session)

        if chat_id:
            qs = qs.filter(chat__chat_id=chat_id)

        if date_from:
            qs = qs.filter(date__date__gte=date_from)

        if date_to:
            qs = qs.filter(date__date__lte=date_to)

        return qs

    def get_overview_stats(self):
        """Get general overview statistics."""
        messages = self.get_messages_queryset()

        total_messages = messages.count()
        total_chats = TelegramChat.objects.filter(session=self.session).count()
        deleted_messages = messages.filter(is_deleted=True).count()
        media_messages = messages.filter(has_media=True).count()
        outgoing_messages = messages.filter(is_outgoing=True).count()

        # Date range
        date_range = messages.aggregate(
            first_message=models.Min('date'),
            last_message=models.Max('date')
        )

        return {
            'total_messages': total_messages,
            'total_chats': total_chats,
            'deleted_messages': deleted_messages,
            'media_messages': media_messages,
            'outgoing_messages': outgoing_messages,
            'incoming_messages': total_messages - outgoing_messages,
            'first_message_date': date_range['first_message'],
            'last_message_date': date_range['last_message'],
        }

    def get_daily_message_counts(self, days=30, chat_id=None):
        """Get message counts per day for the last N days."""
        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        daily_counts = messages.annotate(
            day=TruncDate('date')
        ).values('day').annotate(
            count=Count('id'),
            outgoing=Count('id', filter=Q(is_outgoing=True)),
            incoming=Count('id', filter=Q(is_outgoing=False)),
            deleted=Count('id', filter=Q(is_deleted=True)),
        ).order_by('day')

        return list(daily_counts)

    def get_hourly_activity(self, chat_id=None, days=30):
        """Get message activity by hour of day."""
        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        hourly = messages.annotate(
            hour=ExtractHour('date')
        ).values('hour').annotate(
            count=Count('id')
        ).order_by('hour')

        # Fill in missing hours with 0
        hour_data = {h: 0 for h in range(24)}
        for item in hourly:
            hour_data[item['hour']] = item['count']

        return [{'hour': h, 'count': c} for h, c in hour_data.items()]

    def get_weekly_activity(self, chat_id=None, days=90):
        """Get message activity by day of week (0=Sunday, 6=Saturday)."""
        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        weekly = messages.annotate(
            weekday=ExtractWeekDay('date')
        ).values('weekday').annotate(
            count=Count('id')
        ).order_by('weekday')

        # Day names
        day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
        weekday_data = {i: 0 for i in range(1, 8)}

        for item in weekly:
            weekday_data[item['weekday']] = item['count']

        return [{'day': day_names[i-1], 'day_num': i, 'count': weekday_data[i]} for i in range(1, 8)]

    def get_activity_heatmap(self, days=90, chat_id=None):
        """Get activity data for calendar heatmap."""
        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        daily = messages.annotate(
            day=TruncDate('date')
        ).values('day').annotate(
            count=Count('id')
        ).order_by('day')

        # Convert to dict format for heatmap
        return {str(item['day']): item['count'] for item in daily}

    def get_top_chats(self, limit=10):
        """Get top chats by message count."""
        chats = TelegramChat.objects.filter(
            session=self.session
        ).annotate(
            message_count=Count('messages'),
            deleted_count=Count('messages', filter=Q(messages__is_deleted=True)),
            media_count=Count('messages', filter=Q(messages__has_media=True)),
        ).order_by('-message_count')[:limit]

        return list(chats.values(
            'chat_id', 'title', 'chat_type', 'message_count',
            'deleted_count', 'media_count'
        ))

    def get_top_senders(self, limit=20, chat_id=None, days=30):
        """Get top message senders."""
        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        senders = messages.exclude(
            sender_name=''
        ).values('sender_id', 'sender_name').annotate(
            message_count=Count('id'),
            media_count=Count('id', filter=Q(has_media=True)),
        ).order_by('-message_count')[:limit]

        return list(senders)

    def get_word_frequency(self, limit=100, chat_id=None, days=30, min_word_length=3):
        """Get word frequency from messages."""
        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        # Get all message texts
        texts = messages.exclude(text='').values_list('text', flat=True)

        # Count words
        word_counter = Counter()
        word_pattern = re.compile(r'\b[a-zA-Zа-яА-ЯёЁіІїЇєЄ]+\b', re.UNICODE)

        for text in texts:
            if text:
                words = word_pattern.findall(text.lower())
                words = [w for w in words if len(w) >= min_word_length and w not in self.STOP_WORDS]
                word_counter.update(words)

        return word_counter.most_common(limit)

    def get_media_stats(self, chat_id=None):
        """Get statistics about media files."""
        messages = self.get_messages_queryset(chat_id=chat_id).filter(has_media=True)

        # Count by media type
        media_types = messages.values('media_type').annotate(
            count=Count('id'),
            total_size=Sum('media_file_size'),
        ).order_by('-count')

        # Count downloaded vs not downloaded
        downloaded = messages.exclude(media_file='').exclude(media_file__isnull=True).count()
        not_downloaded = messages.filter(Q(media_file='') | Q(media_file__isnull=True)).count()

        # Total size
        total_size = messages.aggregate(total=Sum('media_file_size'))['total'] or 0

        return {
            'by_type': list(media_types),
            'downloaded': downloaded,
            'not_downloaded': not_downloaded,
            'total_size': total_size,
            'total_count': downloaded + not_downloaded,
        }

    def get_chat_type_distribution(self):
        """Get distribution of chats by type."""
        chats = TelegramChat.objects.filter(session=self.session)

        distribution = chats.values('chat_type').annotate(
            count=Count('id'),
            messages=Count('messages'),
        ).order_by('-count')

        return list(distribution)

    def get_message_length_stats(self, chat_id=None, days=30):
        """Get statistics about message lengths."""
        from django.db.models.functions import Length

        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        messages = messages.exclude(text='').annotate(text_length=Length('text'))

        # Get length distribution
        length_ranges = [
            (0, 10, 'Very Short (1-10)'),
            (11, 50, 'Short (11-50)'),
            (51, 200, 'Medium (51-200)'),
            (201, 500, 'Long (201-500)'),
            (501, 10000, 'Very Long (500+)'),
        ]

        distribution = []
        for min_len, max_len, label in length_ranges:
            count = messages.filter(text_length__gte=min_len, text_length__lte=max_len).count()
            distribution.append({'label': label, 'count': count})

        # Average length
        avg_length = messages.aggregate(avg=models.Avg('text_length'))['avg'] or 0

        return {
            'distribution': distribution,
            'average_length': round(avg_length, 1),
        }

    def get_response_time_stats(self, chat_id=None, days=30):
        """Calculate average response times in conversations."""
        # This is a simplified version - proper implementation would need
        # to track conversation threads
        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        # Get messages ordered by date for each chat
        messages = messages.filter(
            chat__chat_type='user'  # Only private chats
        ).order_by('chat', 'date')

        # Calculate time differences between incoming and outgoing
        response_times = []
        prev_msg = None

        for msg in messages.values('chat_id', 'date', 'is_outgoing')[:1000]:
            if prev_msg and prev_msg['chat_id'] == msg['chat_id']:
                if prev_msg['is_outgoing'] != msg['is_outgoing']:
                    diff = (msg['date'] - prev_msg['date']).total_seconds()
                    if 0 < diff < 86400:  # Less than 24 hours
                        response_times.append(diff)
            prev_msg = msg

        if response_times:
            avg_response = sum(response_times) / len(response_times)
            return {
                'average_seconds': round(avg_response, 1),
                'average_minutes': round(avg_response / 60, 1),
                'sample_size': len(response_times),
            }

        return None

    def get_emoji_stats(self, chat_id=None, days=30, limit=20):
        """Get emoji usage statistics."""
        import emoji

        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        emoji_counter = Counter()

        for text in messages.exclude(text='').values_list('text', flat=True):
            if text:
                emojis = [c for c in text if c in emoji.EMOJI_DATA]
                emoji_counter.update(emojis)

        return emoji_counter.most_common(limit)

    def get_link_stats(self, chat_id=None, days=30):
        """Get statistics about shared links."""
        import re

        date_from = timezone.now().date() - timedelta(days=days)
        messages = self.get_messages_queryset(chat_id=chat_id, date_from=date_from)

        url_pattern = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+')
        domain_counter = Counter()
        total_links = 0

        for text in messages.exclude(text='').values_list('text', flat=True):
            if text:
                urls = url_pattern.findall(text)
                for url in urls:
                    total_links += 1
                    try:
                        from urllib.parse import urlparse
                        domain = urlparse(url).netloc
                        domain_counter[domain] += 1
                    except:
                        pass

        return {
            'total_links': total_links,
            'top_domains': domain_counter.most_common(20),
        }


# Import models at the end to avoid circular imports
from django.db import models
