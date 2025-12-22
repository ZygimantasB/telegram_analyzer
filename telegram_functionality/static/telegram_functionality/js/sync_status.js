// Sync Status Page JavaScript

let pollInterval = null;
let startTime = null;

document.addEventListener('DOMContentLoaded', function() {
    // Parse start time
    if (window.TASK_STARTED_AT) {
        startTime = new Date(window.TASK_STARTED_AT);
    }

    // Start polling if task is not finished
    if (!window.TASK_IS_FINISHED) {
        startPolling();
    } else {
        // Hide activity section for finished tasks
        hideActivitySection();
    }

    // Start elapsed time counter
    updateElapsedTime();
    setInterval(updateElapsedTime, 1000);
});

function startPolling() {
    // Poll every 2 seconds
    pollInterval = setInterval(fetchProgress, 2000);
    // Fetch immediately
    fetchProgress();
}

function stopPolling() {
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

function fetchProgress() {
    fetch(window.SYNC_PROGRESS_URL)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                updateUI(data);

                if (data.is_finished) {
                    stopPolling();
                    hideActivitySection();
                    updateActionButtons(data.status);
                }
            }
        })
        .catch(error => {
            console.error('Error fetching progress:', error);
        });
}

function updateUI(data) {
    // Update status badge
    const statusBadge = document.getElementById('statusBadge');
    statusBadge.className = `badge bg-${data.status} status-badge`;
    statusBadge.textContent = capitalizeFirst(data.status);

    // Update progress bar
    const progressBar = document.getElementById('progressBar');
    const progressPercent = document.getElementById('progressPercent');
    progressBar.style.width = data.progress_percent + '%';
    progressBar.setAttribute('aria-valuenow', data.progress_percent);
    progressPercent.textContent = data.progress_percent + '%';

    // Update progress text
    document.getElementById('syncedChats').textContent = data.synced_chats;
    document.getElementById('totalChats').textContent = data.total_chats;

    // Update current chat
    if (data.current_chat_title) {
        document.getElementById('currentChat').textContent = data.current_chat_title;
    }

    // Update stats
    document.getElementById('totalMessages').textContent = formatNumber(data.total_messages);
    document.getElementById('newMessages').textContent = formatNumber(data.new_messages);
    document.getElementById('syncedChatsCount').textContent = data.synced_chats;
    document.getElementById('syncedUsers').textContent = formatNumber(data.synced_users || 0);

    // Update log
    if (data.log) {
        const logContent = document.getElementById('logContent');
        logContent.textContent = data.log;
        // Auto-scroll to bottom
        logContent.scrollTop = logContent.scrollHeight;
    }

    // Update error message
    if (data.error_message) {
        showError(data.error_message);
    }

    // Update start time if not set
    if (data.started_at && !startTime) {
        startTime = new Date(data.started_at);
        document.getElementById('startedAt').textContent = formatDateTime(startTime);
    }

    // Update completed time
    if (data.completed_at) {
        const completedAt = new Date(data.completed_at);
        let completedSpan = document.getElementById('completedAt');
        if (!completedSpan) {
            // Add completed timestamp if it doesn't exist
            const timestampDiv = document.querySelector('.text-muted.small.mt-3');
            const span = document.createElement('span');
            span.className = 'ms-3';
            span.innerHTML = 'Completed: <span id="completedAt">' + formatDateTime(completedAt) + '</span>';
            timestampDiv.appendChild(span);
        } else {
            completedSpan.textContent = formatDateTime(completedAt);
        }
    }

    // Remove animation when finished
    if (data.is_finished) {
        progressBar.classList.remove('progress-bar-animated', 'progress-bar-striped');

        if (data.status === 'completed') {
            progressBar.classList.add('bg-success');
        } else if (data.status === 'failed') {
            progressBar.classList.add('bg-danger');
        } else if (data.status === 'cancelled') {
            progressBar.classList.add('bg-secondary');
        }
    }
}

function hideActivitySection() {
    const activitySection = document.getElementById('currentActivitySection');
    if (activitySection) {
        activitySection.style.display = 'none';
    }
}

function updateActionButtons(status) {
    const actionButtons = document.getElementById('actionButtons');
    let html = '';

    if (status === 'completed' || status === 'failed' || status === 'cancelled') {
        html = `
            <a href="${window.location.pathname.replace(/sync-status\/\d+/, 'start-sync')}" class="btn btn-primary">
                <i class="bi bi-arrow-repeat"></i> Start New Sync
            </a>
        `;
    }

    actionButtons.innerHTML = html;
}

function cancelSync() {
    if (!confirm('Are you sure you want to cancel the sync?')) {
        return;
    }

    const cancelBtn = document.getElementById('cancelBtn');
    cancelBtn.disabled = true;
    cancelBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Cancelling...';

    fetch(window.CANCEL_SYNC_URL, {
        method: 'POST',
        headers: {
            'X-CSRFToken': window.CSRF_TOKEN,
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Will be updated by next poll
            fetchProgress();
        } else {
            alert(data.error || 'Failed to cancel sync');
            cancelBtn.disabled = false;
            cancelBtn.innerHTML = '<i class="bi bi-x-circle"></i> Cancel Sync';
        }
    })
    .catch(error => {
        alert('An error occurred');
        cancelBtn.disabled = false;
        cancelBtn.innerHTML = '<i class="bi bi-x-circle"></i> Cancel Sync';
    });
}

function toggleLog() {
    const logContainer = document.getElementById('logContainer');
    const icon = document.getElementById('logToggleIcon');

    if (logContainer.style.display === 'none') {
        logContainer.style.display = 'block';
        icon.className = 'bi bi-chevron-down';
    } else {
        logContainer.style.display = 'none';
        icon.className = 'bi bi-chevron-up';
    }
}

function showError(message) {
    let errorAlert = document.getElementById('errorAlert');
    if (!errorAlert) {
        const cardBody = document.querySelector('.card-body');
        const alertDiv = document.createElement('div');
        alertDiv.className = 'alert alert-danger mt-3';
        alertDiv.id = 'errorAlert';
        alertDiv.innerHTML = '<i class="bi bi-exclamation-triangle"></i> <span id="errorMessage"></span>';
        cardBody.appendChild(alertDiv);
        errorAlert = alertDiv;
    }
    document.getElementById('errorMessage').textContent = message;
    errorAlert.style.display = 'block';
}

function updateElapsedTime() {
    if (!startTime) return;

    const now = new Date();
    const diff = Math.floor((now - startTime) / 1000);

    const hours = Math.floor(diff / 3600);
    const minutes = Math.floor((diff % 3600) / 60);
    const seconds = diff % 60;

    let timeStr = '';
    if (hours > 0) {
        timeStr = `${hours}:${pad(minutes)}:${pad(seconds)}`;
    } else {
        timeStr = `${minutes}:${pad(seconds)}`;
    }

    document.getElementById('elapsedTime').textContent = timeStr;
}

function formatNumber(num) {
    return num.toLocaleString();
}

function formatDateTime(date) {
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function capitalizeFirst(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function pad(num) {
    return num.toString().padStart(2, '0');
}
