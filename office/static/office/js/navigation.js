document.addEventListener('DOMContentLoaded', () => {
    const menus = Array.from(document.querySelectorAll('.nav-menu'));

    menus.forEach((menu) => {
        menu.addEventListener('toggle', () => {
            if (!menu.open) return;
            menus.forEach((otherMenu) => {
                if (otherMenu !== menu) otherMenu.open = false;
            });
        });
    });

    document.addEventListener('click', (event) => {
        if (event.target.closest('.nav-menu')) return;
        menus.forEach((menu) => { menu.open = false; });
    });

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        menus.forEach((menu) => { menu.open = false; });
    });
});
