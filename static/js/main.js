// MedSupply Rescue Client Helper
(() => {
    const sidebar = document.getElementById('appSidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');

    function closeSidebar() {
        if (!sidebar || !sidebarBackdrop || !sidebarToggle) return;
        sidebar.classList.add('-translate-x-full');
        sidebarBackdrop.classList.add('hidden');
        sidebarBackdrop.classList.remove('block');
        sidebarToggle.setAttribute('aria-expanded', 'false');
        document.body.classList.remove('overflow-hidden');
    }

    function openSidebar() {
        if (!sidebar || !sidebarBackdrop || !sidebarToggle) return;
        sidebar.classList.remove('-translate-x-full');
        sidebarBackdrop.classList.remove('hidden');
        sidebarBackdrop.classList.add('block');
        sidebarToggle.setAttribute('aria-expanded', 'true');
        document.body.classList.add('overflow-hidden');
    }

    if (sidebar && sidebarToggle && sidebarBackdrop) {
        sidebarToggle.addEventListener('click', () => {
            if (sidebarToggle.getAttribute('aria-expanded') === 'true') {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
        sidebarBackdrop.addEventListener('click', closeSidebar);
        sidebar.querySelectorAll('nav a').forEach((link) => {
            link.addEventListener('click', () => {
                if (window.matchMedia('(max-width: 1023px)').matches) closeSidebar();
            });
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') closeSidebar();
        });
        window.addEventListener('resize', () => {
            if (window.matchMedia('(min-width: 1024px)').matches) closeSidebar();
        });
    }

    async function loadPaginatedResults(url, addHistory) {
        const currentResults = document.querySelector('[data-paginated-results]');
        if (!currentResults) return false;

        currentResults.setAttribute('aria-busy', 'true');
        currentResults.classList.add('opacity-60', 'pointer-events-none');

        try {
            const response = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });
            if (!response.ok) throw new Error(`Pagination request failed: ${response.status}`);

            const html = await response.text();
            const page = new DOMParser().parseFromString(html, 'text/html');
            const newResults = page.querySelector(
                `[data-paginated-results="${currentResults.dataset.paginatedResults}"]`
            );
            if (!newResults) throw new Error('Paginated results were missing from the response.');

            currentResults.replaceWith(newResults);
            if (addHistory) history.pushState({ paginated: true }, '', url);
            return true;
        } catch (error) {
            console.error('Unable to update paginated results:', error);
            return false;
        } finally {
            const results = document.querySelector('[data-paginated-results]');
            if (results) {
                results.removeAttribute('aria-busy');
                results.classList.remove('opacity-60', 'pointer-events-none');
            }
        }
    }

    document.addEventListener('click', async (event) => {
        const link = event.target.closest('a[data-ajax-pagination]');
        if (!link || event.defaultPrevented || event.button !== 0 ||
            event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

        const target = new URL(link.href, window.location.href);
        if (target.origin !== window.location.origin) return;

        event.preventDefault();
        const loaded = await loadPaginatedResults(target.href, true);
        if (!loaded) window.location.assign(target.href);
    });

    window.addEventListener('popstate', async () => {
        if (!document.querySelector('[data-paginated-results]')) return;
        const loaded = await loadPaginatedResults(window.location.href, false);
        if (!loaded) window.location.reload();
    });
})();
