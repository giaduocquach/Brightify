import { useEffect, useState } from 'react';
import { useStore } from '../state/store';

// The vibe of the current song in one word, derived from its valence-arousal quadrant. Appears
// briefly on track change (then fades) so the user can name what they're feeling. Decorative
// (aria-hidden) — the now-playing aria-live region already announces the track for SR users.
function moodWord(valence: number, arousal: number): string {
  if (arousal >= 0.5) return valence >= 0.5 ? 'Sôi động' : 'Mãnh liệt';
  return valence >= 0.5 ? 'Thư thái' : 'Tự sự';
}

const SHOW_MS = 3600;

export default function MoodWord() {
  const current = useStore((s) => s.current);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    if (!current) return;
    setVisible(true);
    const id = setTimeout(() => setVisible(false), SHOW_MS);
    return () => clearTimeout(id);
  }, [current?.track_id, current]);

  if (!current || !visible) return null;
  return <div className="mood-word" aria-hidden="true">{moodWord(current.valence, current.arousal)}</div>;
}
