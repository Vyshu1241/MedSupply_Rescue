// MedSupply Rescue Client Helper
(() => {
    const sidebar = document.getElementById('appSidebar');
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');
    const appContent = document.getElementById('appContent');
    const desktopNavigation = window.matchMedia('(min-width: 1024px)');

    function syncSidebarTooltips(collapsed) {
        if (!sidebar) return;
        sidebar.querySelectorAll('a[data-sidebar-tooltip]').forEach((link) => {
            if (collapsed) link.title = link.dataset.sidebarTooltip;
            else link.removeAttribute('title');
        });
    }

    function closeSidebar() {
        if (!sidebar || !sidebarBackdrop || !sidebarToggle) return;
        sidebar.classList.remove('-translate-x-full');
        sidebar.classList.add('lg:translate-x-0');
        document.body.classList.add('sidebar-collapsed');
        sidebarBackdrop.classList.add('hidden');
        sidebarBackdrop.classList.remove('block');
        sidebarToggle.setAttribute('aria-expanded', 'false');
        sidebarToggle.setAttribute('aria-label', 'Expand sidebar');
        document.body.classList.remove('overflow-hidden');
        syncSidebarTooltips(desktopNavigation.matches);
    }

    function openSidebar() {
        if (!sidebar || !sidebarBackdrop || !sidebarToggle) return;
        sidebar.classList.remove('-translate-x-full');
        sidebar.classList.add('lg:translate-x-0');
        if (appContent) appContent.classList.add('lg:pl-64');
        document.body.classList.remove('sidebar-collapsed');
        if (desktopNavigation.matches) {
            sidebarBackdrop.classList.add('hidden');
            sidebarBackdrop.classList.remove('block');
            document.body.classList.remove('overflow-hidden');
        } else {
            sidebarBackdrop.classList.remove('hidden');
            sidebarBackdrop.classList.add('block');
            document.body.classList.add('overflow-hidden');
        }
        sidebarToggle.setAttribute('aria-expanded', 'true');
        sidebarToggle.setAttribute('aria-label', 'Collapse sidebar');
        syncSidebarTooltips(false);
    }

    if (sidebar && sidebarToggle && sidebarBackdrop) {
        if (desktopNavigation.matches) openSidebar();
        else closeSidebar();

        sidebarToggle.addEventListener('click', () => {
            if (sidebarToggle.getAttribute('aria-expanded') === 'true') {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
        sidebarBackdrop.addEventListener('click', closeSidebar);
        sidebar.querySelectorAll('a').forEach((link) => {
            link.addEventListener('click', () => {
                if (window.matchMedia('(max-width: 1023px)').matches) closeSidebar();
            });
        });
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && sidebarToggle.getAttribute('aria-expanded') === 'true') {
                closeSidebar();
            }
        });
        window.addEventListener('resize', () => {
            if (desktopNavigation.matches) openSidebar();
            else closeSidebar();
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
