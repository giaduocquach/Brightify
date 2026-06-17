import { useState } from 'react';
import type { ColorResult, Song } from '../api/client';
import VACircumplex from './VACircumplex';

// On-demand "why these songs" explainer (progressive disclosure — collapsed by default so it
// never clutters the immersive view). Expands the V-A circumplex + a one-line grounding so a
// newcomer understands the colour → emotion → music chain. Cited for thesis defence.
export default function WhyColorPanel({ bridge, songs }: { bridge: ColorResult['bridge']; songs: Song[] }) {
  const [open, setOpen] = useState(false);
  if (!bridge || !bridge.length) return null;
  return (
    <div className="whycolor">
      <button className="whycolor-toggle" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        Vì sao màu này? <span aria-hidden="true">{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="whycolor-body">
          <VACircumplex bridge={bridge} songs={songs} />
          <p className="whycolor-note">
            Màu mang cảm xúc; những bài cùng vùng <strong>Valence–Arousal</strong> (vui–buồn ×
            tĩnh–động) được chọn. Vũ trụ cũng ấm lên khi cảm xúc tích cực hơn.
          </p>
          <p className="whycolor-cite">Palmer &amp; Schloss, PNAS 2013</p>
        </div>
      )}
    </div>
  );
}
