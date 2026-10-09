(() => {
    const key = 'bendango-theme';
    const root = document.documentElement;
    const system = window.matchMedia('(prefers-color-scheme: dark)');
    let preference = null;
    let button;
    try {
        const saved = localStorage.getItem(key);
        if (saved === 'dark' || saved === 'light') preference = saved;
    } catch (_) { /* The toggle also works when browser storage is unavailable. */ }

    function apply() {
        const dark = preference ? preference === 'dark' : system.matches;
        root.classList.toggle('dark', dark);
        if (button) {
            button.setAttribute('aria-pressed', String(dark));
            button.title = dark ? 'Activer le thème clair' : 'Activer le thème sombre';
        }
    }
    apply();
    system.addEventListener('change', apply);
    window.addEventListener('storage', (event) => {
        if (event.key !== key && event.key !== null) return;
        preference = event.newValue === 'dark' || event.newValue === 'light' ? event.newValue : null;
        apply();
    });
    document.addEventListener('DOMContentLoaded', () => {
        button = document.getElementById('theme-toggle');
        if (!button) return;
        apply();
        button.hidden = false;
        button.addEventListener('click', () => {
            preference = root.classList.contains('dark') ? 'light' : 'dark';
            try { localStorage.setItem(key, preference); } catch (_) { /* Keep the choice for this page. */ }
            apply();
        });
    });
})();
