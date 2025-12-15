document.getElementById('resendCode').addEventListener('click', function() {
    this.disabled = true;
    this.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sending...';

    fetch(window.RESEND_CODE_URL, {
        method: 'POST',
        headers: {
            'X-CSRFToken': window.CSRF_TOKEN,
            'X-Requested-With': 'XMLHttpRequest'
        }
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            alert('Code resent successfully!');
        } else {
            alert(data.error || 'Failed to resend code');
        }
    })
    .catch(error => {
        alert('An error occurred');
    })
    .finally(() => {
        this.disabled = false;
        this.innerHTML = 'Resend Code';
    });
});
