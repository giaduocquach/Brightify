import { useStore } from '../state/store';

// First-load greeting. The astronaut (in the 3D scene) floats in and asks where to
// go; this overlay carries the words + the call to action that reveals the system.
export default function Intro() {
  const enterSystem = useStore((s) => s.enterSystem);

  return (
    <div className="intro">
      <div className="intro-card">
        <span className="intro-badge">BRIGHTIFY · DU HÀNH CẢM XÚC</span>
        <h1 className="home-title">Hôm nay bạn muốn đi đâu?</h1>
        <p className="home-sub">
          Một phi hành gia đang chờ đưa bạn qua 12 hành tinh cảm xúc.
          <span className="home-hint"> Chạm một hành tinh để khám phá, hoặc chọn hai để du hành giữa chúng.</span>
        </p>
        <button className="intro-cta" onClick={enterSystem}>Bắt đầu khám phá <span aria-hidden="true">✦</span></button>
      </div>
    </div>
  );
}
