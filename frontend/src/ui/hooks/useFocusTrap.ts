import { useEffect, useRef } from 'react';

// Shared modal focus management for aria-modal dialogs (SearchOverlay, GuideOverlay).
// Two responsibilities folded into one hook so both overlays stay consistent (WCAG 2.1.2 +
// 2.4.3): (1) trap Tab/Shift+Tab inside the dialog while open, (2) remember what had focus on
// open and hand it back on close. Returns a ref to attach to the dialog container.
const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function useFocusTrap<T extends HTMLElement = HTMLDivElement>(
  active: boolean,
  initialFocus?: React.RefObject<HTMLElement | null>,
) {
  const containerRef = useRef<T>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!active) return;
    const container = containerRef.current;
    restoreFocus.current = document.activeElement as HTMLElement | null;

    // Defer initial focus a tick so the dialog is painted before we move focus into it.
    const id = setTimeout(() => (initialFocus?.current ?? container)?.focus(), 0);

    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Tab' || !container) return;
      const nodes = container.querySelectorAll<HTMLElement>(FOCUSABLE);
      if (nodes.length === 0) {
        e.preventDefault();
        container.focus();
        return;
      }
      const first = nodes[0];
      const last = nodes[nodes.length - 1];
      const focused = document.activeElement as HTMLElement | null;
      // Focus escaped the dialog (or is on the container) — pull it back in.
      if (!container.contains(focused)) {
        e.preventDefault();
        first.focus();
      } else if (e.shiftKey && focused === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && focused === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', onKey, true);

    return () => {
      clearTimeout(id);
      document.removeEventListener('keydown', onKey, true);
      restoreFocus.current?.focus();
    };
  }, [active, initialFocus]);

  return containerRef;
}
