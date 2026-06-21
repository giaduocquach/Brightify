// Faint mood-coloured vignette framing the cosmic scene in the now-playing song's emotion
// colour. Reads the document-level `--mood` custom property (written in App on song change),
// so it shares the single mood→colour channel with the player and the 3D vibe layer. Purely
// decorative: aria-hidden + pointer-events:none, sits just above the canvas, below all chrome.
export default function MoodVeil() {
  return <div className="mood-veil" aria-hidden="true" />;
}
