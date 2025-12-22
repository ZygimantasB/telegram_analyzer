function toggleDeleted() {
    const checkbox = document.getElementById('showDeleted');
    const url = new URL(window.location);
    if (checkbox.checked) {
        url.searchParams.set('show_deleted', 'true');
    } else {
        url.searchParams.delete('show_deleted');
    }
    url.searchParams.set('page', '1');
    window.location = url;
}

async function downloadMedia(messageId, button) {
    // Disable button and show loading
    button.disabled = true;
    const originalHtml = button.innerHTML;
    button.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Downloading...';

    try {
        const response = await fetch(`/telegram/media/${messageId}/trigger-download/`, {
            method: 'GET',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            }
        });

        const data = await response.json();

        if (data.success) {
            // Success - replace button with success message and refresh link
            const placeholder = button.closest('.media-placeholder');
            placeholder.innerHTML = `
                <div class="alert alert-success py-2 px-3 mb-0">
                    <i class="bi bi-check-circle"></i> Downloaded: ${data.file_name || 'File'}
                    ${data.file_size ? `(${(data.file_size / 1024 / 1024).toFixed(2)} MB)` : ''}
                    <br>
                    <small class="text-muted">Refresh the page to view the media.</small>
                </div>
            `;
        } else {
            // Error
            button.innerHTML = `<i class="bi bi-x-circle"></i> ${data.error || 'Failed'}`;
            button.classList.remove('btn-outline-primary');
            button.classList.add('btn-outline-danger');
            button.disabled = false;

            // Reset after 3 seconds
            setTimeout(() => {
                button.innerHTML = originalHtml;
                button.classList.remove('btn-outline-danger');
                button.classList.add('btn-outline-primary');
            }, 3000);
        }
    } catch (error) {
        button.innerHTML = '<i class="bi bi-x-circle"></i> Error';
        button.classList.remove('btn-outline-primary');
        button.classList.add('btn-outline-danger');

        setTimeout(() => {
            button.innerHTML = originalHtml;
            button.classList.remove('btn-outline-danger');
            button.classList.add('btn-outline-primary');
            button.disabled = false;
        }, 3000);
    }
}
