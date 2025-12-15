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
