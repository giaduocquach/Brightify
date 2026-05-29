// ══════════════════════════════════════════════════════════════════════════
// App Bootstrap
// (The manual "Hôm nay" context tab was removed — context now lives on the Home
//  "Ngay bây giờ" shelf. This file keeps app init + global exports.)
// ══════════════════════════════════════════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => app.init());

window.app = app;
window.router = router;
