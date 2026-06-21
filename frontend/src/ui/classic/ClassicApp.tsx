import ClassicTopbar from './ClassicTopbar';
import ClassicSidebar from './ClassicSidebar';
import ClassicMain from './ClassicMain';
import PlayerBar from '../PlayerBar';
import LyricsPanel from '../LyricsPanel';

// The classic skin: a conventional music-web layout (topbar · sidebar · main · player bar),
// reusing the shared store, audio engine, and 2D components. No 3D canvas is mounted, so a
// classic-first session never pays the WebGL / three.js cost. Lyrics ride as an overlay
// (LyricsPanel returns null unless showLyrics) just like the immersive skin.
export default function ClassicApp() {
  return (
    <div className="classic-root">
      <ClassicTopbar />
      <div className="classic-body">
        <ClassicSidebar />
        <ClassicMain />
      </div>
      <PlayerBar />
      <LyricsPanel />
    </div>
  );
}
