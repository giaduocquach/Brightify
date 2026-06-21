import { useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import { Html, Outlines } from '@react-three/drei';
import { AdditiveBlending, Color, DoubleSide, Group, Matrix4, type Mesh, type MeshBasicMaterial, Quaternion, Sprite, SpriteMaterial, Vector3 } from 'three';
import { useStore } from '../../state/store';
import { engine } from '../../audio/engine';
import { vaToColor } from '../va';
import { solarRefs } from './refs';
import { bodyByHex } from './bodies';
import { glowTexture } from './glow';
import { starShape } from './shapes';
import { toonRamp, OUTLINE } from './toon';
import { expressionFor, easeExpression, NEUTRAL, type Expression } from './character/face';

interface Line { vi: string; en: string; }
const SPEECH: Record<string, Line> = {
  intro: { vi: 'Đi đâu hôm nay? ✨', en: 'Where to today?' },
  system: { vi: 'Chạm một hành tinh nhé!', en: 'Tap a planet!' },
};

// Distance (local model units) from the group origin down to the soles — used to lift
// the runner so its feet sit ON the planet surface instead of sinking in. Derived from
// the robot leg chain: foot bottom = legL(-0.28) + shinL(-0.18) + foot(-0.15 - 0.07) = -0.68.
// The lift (FOOT_DROP * scale) cancels the scaled foot depth for ANY planet size, so the
// soles land on the surface regardless of the body's radius.
const FOOT_DROP = 0.68;

// A cel-shaded CHIBI Vietnamese astronaut mascot: oversized helmet head with a friendly FACE
// behind the visor (big eyes, smile, rosy cheeks), round stubby body + limbs, ink outline. Keeps
// the VN identity — gold star on the helmet, a red flag patch with the gold star on the chest, an
// Đông Sơn ring of gold studs at the waist. Animation (kept from the motion overhaul): blink, idle
// tether sway, run squash-&-stretch, hop, float, wave, rising music notes. In first-person flight
// we ARE the pilot, so the body isn't drawn (the cockpit shows the dashboard instead).
export default function Astronaut() {
  const camera = useThree((s) => s.camera);
  const ramp = toonRamp();
  const root = useRef<Group>(null);
  const bob = useRef<Group>(null);
  const legL = useRef<Group>(null);
  const legR = useRef<Group>(null);
  const shinL = useRef<Group>(null);
  const shinR = useRef<Group>(null);
  const armL = useRef<Group>(null);
  const armR = useRef<Group>(null);
  const eyeL = useRef<Group>(null);
  const eyeR = useRef<Group>(null);
  const browL = useRef<Mesh>(null);
  const browR = useRef<Mesh>(null);
  const mouth = useRef<Group>(null);
  const cheekL = useRef<Mesh>(null);
  const cheekR = useRef<Mesh>(null);

  const mode = useStore((s) => s.mode);
  const sel = useStore((s) => s.selectedColors);
  const current = useStore((s) => s.current);
  // Accent = the NOW-PLAYING song's mood colour (falls back to the selected planet, then a default).
  // Drives the chest light, visor glow and music notes so the mascot wears the song's emotion.
  const accent = useMemo(
    () => (current ? vaToColor(current.valence, current.arousal) : new Color(sel[0] || '#7cc7ff')),
    [current, sel],
  );
  // Target facial expression for the current song; eased toward each frame (recomputed per track).
  const exprTarget = useMemo<Expression>(
    () => (current ? expressionFor(current.valence, current.arousal) : NEUTRAL),
    [current],
  );
  const expr = useRef<Expression>({ ...NEUTRAL });
  const bubble: Line | undefined = SPEECH[mode];

  const star = useMemo(() => starShape(0.07, 0.03), []);
  const tex = glowTexture();

  const noteSpriteRefs = useRef<(Sprite | null)[]>([]);
  const noteY = useRef([0, 0.9, 1.8]);

  const tmp = useRef(new Vector3());
  const baseVec = useRef(new Vector3());
  const up = useRef(new Vector3());
  const fwd = useRef(new Vector3());
  const xAxis = useRef(new Vector3());
  const m4 = useRef(new Matrix4());
  const quat = useRef(new Quaternion());
  const frozenT = useRef(0); // last live time → reduced-motion holds a static pose

  useFrame((state, dt) => {
    if (!root.current) return;
    const k = 1 - Math.pow(0.002, dt);
    const g = root.current;
    const rm = solarRefs.reducedMotion;
    if (!rm) frozenT.current = state.clock.elapsedTime;
    const t = rm ? frozenT.current : state.clock.elapsedTime; // freeze limb/bob/blink cycles

    const running = mode === 'explore' && solarRefs.runnerActive && !!sel[0];
    const boarding = mode === 'boarding' && solarRefs.runnerActive && !!sel[0];
    const waving = mode === 'intro';

    if (running || boarding) {
      const size = bodyByHex(sel[0])?.size ?? 0.5;
      const scale = Math.max(0.045, size * 0.12);
      // body-appropriate "up" (radial for walk/hop/float; ring-plane normal for ringwalk)
      up.current.copy(solarRefs.runnerUp);
      if (up.current.lengthSq() < 1e-4) up.current.set(0, 1, 0); else up.current.normalize();
      baseVec.current.copy(solarRefs.runnerPos).addScaledVector(up.current, FOOT_DROP * scale);

      if (boarding) {
        // drawn straight up the tractor beam toward the saucer underside, fading near the top
        const lift = solarRefs.boardingLift;
        tmp.current.lerpVectors(baseVec.current, solarRefs.boardingTarget, lift);
        g.position.lerp(tmp.current, Math.min(1, dt * 10));
        const fade = lift > 0.85 ? Math.max(0.01, 1 - (lift - 0.85) / 0.15) : 1;
        g.scale.setScalar(scale * fade);
      } else {
        g.position.lerp(baseVec.current, k);
        g.scale.setScalar(scale);
      }

      // orient feet toward `up` (the body-appropriate surface), nose along forward
      fwd.current.copy(solarRefs.runnerForward).normalize();
      xAxis.current.copy(up.current).cross(fwd.current).normalize();
      fwd.current.copy(xAxis.current).cross(up.current).normalize();
      m4.current.makeBasis(xAxis.current, up.current, fwd.current);
      quat.current.setFromRotationMatrix(m4.current);
      g.quaternion.slerp(quat.current, k);
    } else {
      tmp.current.set(-1.2, -0.95, -3.3).applyMatrix4(camera.matrixWorld);
      g.position.lerp(tmp.current, k);
      g.quaternion.slerp(camera.quaternion, k);
      g.scale.setScalar(0.44);
    }

    // ── animation BY STANCE (walk/ringwalk run-cycle · hop tuck · float arms-out) ──
    const stance = solarRefs.runnerStance;
    const stepping = running && (stance === 'walk' || stance === 'ringwalk');
    const hopping = running && stance === 'hop';
    const floating = running && stance === 'float';
    const cad = t * (hopping ? 5 : 7);
    const sw = Math.sin(cad);
    // Dance overlay: an upbeat song makes the idle mascot bop to the beat (reduced-motion off).
    const dancing = !rm && !!current && current.arousal > 0.62 && current.valence > 0.55 && !stepping && !hopping;
    const danceBeat = dancing ? (0.5 + 0.5 * Math.sin(t * 6)) * (0.6 + engine.features.bass) : 0;

    if (bob.current) {
      if (stepping) {
        bob.current.position.y = Math.abs(Math.sin(cad)) * 0.05;
        const sq = Math.max(0, -sw) * 0.12;
        bob.current.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
        bob.current.rotation.x = 0;
      } else if (hopping) {
        const sq = (1 - Math.abs(Math.sin(t * 2))) * 0.1; // squash on landing (syncs with hop air)
        bob.current.position.y = 0;
        bob.current.scale.set(1 + sq * 0.6, 1 - sq, 1 + sq * 0.6);
        bob.current.rotation.x = 0;
      } else {
        bob.current.position.y = Math.sin(t * 0.9) * 0.04 + danceBeat * 0.06; // breathe (+ bounce when dancing)
        const ds = danceBeat * 0.05;
        bob.current.scale.set(1 + ds, 1 - ds, 1 + ds);
        bob.current.rotation.x = 0;
      }
    }
    if (legL.current && legR.current && shinL.current && shinR.current) {
      if (stepping) {
        legL.current.rotation.x = sw * 0.6; legR.current.rotation.x = -sw * 0.6;
        shinL.current.rotation.x = Math.max(0, -sw) * 1.2; shinR.current.rotation.x = Math.max(0, sw) * 1.2;
      } else if (hopping) {
        const tuck = Math.abs(Math.sin(t * 2)) * 0.8;
        legL.current.rotation.x = tuck; legR.current.rotation.x = tuck;
        shinL.current.rotation.x = tuck * 1.2; shinR.current.rotation.x = tuck * 1.2;
      } else {
        const dangle = floating ? 0.15 : 0;
        legL.current.rotation.x = dangle; legR.current.rotation.x = dangle;
        shinL.current.rotation.x = 0; shinR.current.rotation.x = 0;
      }
    }
    if (armL.current && armR.current) {
      if (waving) {
        armR.current.rotation.z = -2.3; armR.current.rotation.x = Math.sin(t * 6) * 0.4;
        armL.current.rotation.z = 0.2; armL.current.rotation.x = 0;
      } else if (floating) {
        armL.current.rotation.z = 0.95; armR.current.rotation.z = -0.95; // arms out
        const sway = Math.sin(t * 1.2) * 0.15;
        armL.current.rotation.x = sway; armR.current.rotation.x = -sway;
      } else {
        const run = stepping ? sw * 0.5 : 0;
        armL.current.rotation.z = 0.2 + danceBeat * 0.7; armR.current.rotation.z = -0.2 - danceBeat * 0.7;
        armL.current.rotation.x = -run; armR.current.rotation.x = run;
      }
    }
    // ── face: ease toward the song's mood expression, then drive eyes/brows/mouth/cheeks ──
    easeExpression(expr.current, exprTarget, 1 - Math.pow(0.01, dt)); // ~0.5s melt on track change
    const e = expr.current;
    const pulse = rm ? 0 : engine.features.bass; // tiny beat liveliness
    // blink: a quick lid-close every ~4.5s (0.2s V-shaped dip), multiplied onto the mood eye-open
    const cyc = t % 4.5;
    let blink = 1;
    if (cyc > 4.3) blink = 0.1 + 0.9 * Math.abs((cyc - 4.3) / 0.2 - 0.5) * 2;
    const open = (e.eyeOpen + pulse * 0.15) * blink;
    if (eyeL.current && eyeR.current) { eyeL.current.scale.y = open; eyeR.current.scale.y = open; }
    if (browL.current && browR.current) {
      const by = 0.7 + e.browLift * 0.03;
      browL.current.position.y = by; browR.current.position.y = by;
      browL.current.rotation.z = e.browTilt * 0.4; browR.current.rotation.z = -e.browTilt * 0.4;
    }
    if (mouth.current) {
      // flip the smile arc to a frown via negative Y-scale; widen + open with the mood
      const mag = 0.5 + Math.abs(e.mouthCurve) * 0.9 + (e.mouthOpen + pulse * 0.2) * 0.5;
      mouth.current.scale.set(0.8 + Math.abs(e.mouthCurve) * 0.4, (e.mouthCurve >= 0 ? 1 : -1) * mag, 1);
    }
    if (cheekL.current && cheekR.current) {
      (cheekL.current.material as MeshBasicMaterial).opacity = e.blush;
      (cheekR.current.material as MeshBasicMaterial).opacity = e.blush;
    }

    // ── add life: a gentle idle tether sway when not actively walking/hopping ──
    if (bob.current) {
      const idle = !stepping && !hopping;
      bob.current.rotation.z = idle && !rm ? Math.sin(t * 0.5) * 0.04 : 0;
      bob.current.position.x = idle && !rm ? Math.sin(t * 0.37) * 0.015 : 0;
    }

    // ── music notes: 3 glow sprites rising above the astronaut (hidden under reduced-motion) ──
    const noteVisible = (running || boarding) && !rm;
    const noteXZ: [number, number][] = [[0.55, 0.2], [-0.45, -0.25], [0.65, -0.05]];
    noteSpriteRefs.current.forEach((s, i) => {
      if (!s) return;
      s.visible = noteVisible;
      if (!noteVisible) return;
      noteY.current[i] = (noteY.current[i] + dt * 0.7) % 2.4;
      const y = noteY.current[i];
      s.position.set(noteXZ[i][0] + Math.sin(t * 0.8 + i) * 0.03, y + 0.4, noteXZ[i][1]);
      const fade = y < 0.6 ? y / 0.6 : y > 1.9 ? (2.4 - y) / 0.5 : 1;
      (s.material as SpriteMaterial).opacity = Math.max(0, fade * 0.72);
    });
  });

  // Two-colour system: a white body + neutral steel structure, with EVERYTHING that glows
  // (LED face, chest core, ears, antennae, trim) reading in the now-playing mood colour (accent).
  const SUIT = '#eef1f7';        // white body — the one neutral
  const SUIT_D = '#9aa3b8';      // steel grey — joints / bezel / feet
  const SKIN_SCREEN = '#0a0d18'; // dark screen the LED face glows on

  // First-person flight: we ARE the pilot → the body isn't drawn (cockpit shows the dashboard).
  if (mode === 'journey' || mode === 'fly') return null;

  // LED face glows in the now-playing mood (accent); body is light toon metal with an ink outline.
  const LED = accent;
  return (
    <group ref={root}>
      <group ref={bob}>
        {/* ── robot head: rounded shell + dark glossy SCREEN that the LED face glows on ── */}
        <mesh position={[0, 0.62, 0]} scale={[1.12, 0.98, 0.96]}>
          <sphereGeometry args={[0.46, 32, 32]} />
          <meshToonMaterial color={SUIT} gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        {/* dark screen panel (slightly proud, curved) */}
        <mesh position={[0, 0.62, 0.34]} scale={[0.92, 0.76, 0.26]}>
          <sphereGeometry args={[0.42, 28, 28]} />
          <meshStandardMaterial color={SKIN_SCREEN} roughness={0.3} metalness={0.15} emissive={LED} emissiveIntensity={0.12} />
        </mesh>
        {/* screen bezel */}
        <mesh position={[0, 0.62, 0.31]} rotation={[0.05, 0, 0]}>
          <torusGeometry args={[0.34, 0.022, 12, 36]} />
          <meshToonMaterial color={SUIT_D} gradientMap={ramp} />
        </mesh>

        {/* ── LED FACE: glowing eyes + brow bars + mouth + cheek dots (drive the same refs) ── */}
        <group ref={eyeL} position={[-0.17, 0.64, 0.49]}>
          <mesh scale={[0.95, 1.2, 0.5]}><sphereGeometry args={[0.085, 18, 18]} /><meshStandardMaterial color="#d7fbff" emissive={LED} emissiveIntensity={2.4} toneMapped={false} /></mesh>
        </group>
        <group ref={eyeR} position={[0.17, 0.64, 0.49]}>
          <mesh scale={[0.95, 1.2, 0.5]}><sphereGeometry args={[0.085, 18, 18]} /><meshStandardMaterial color="#d7fbff" emissive={LED} emissiveIntensity={2.4} toneMapped={false} /></mesh>
        </group>
        {/* brow bars — biggest expressivity lever (lift + tilt driven by mood) */}
        <mesh ref={browL} position={[-0.17, 0.76, 0.5]}><boxGeometry args={[0.13, 0.026, 0.02]} /><meshStandardMaterial color="#d7fbff" emissive={LED} emissiveIntensity={2} toneMapped={false} /></mesh>
        <mesh ref={browR} position={[0.17, 0.76, 0.5]}><boxGeometry args={[0.13, 0.026, 0.02]} /><meshStandardMaterial color="#d7fbff" emissive={LED} emissiveIntensity={2} toneMapped={false} /></mesh>
        {/* cheek dots — opacity tracks arousal (blush) */}
        <mesh ref={cheekL} position={[-0.27, 0.54, 0.45]}><sphereGeometry args={[0.05, 12, 12]} /><meshBasicMaterial color={accent} transparent opacity={0.85} /></mesh>
        <mesh ref={cheekR} position={[0.27, 0.54, 0.45]}><sphereGeometry args={[0.05, 12, 12]} /><meshBasicMaterial color={accent} transparent opacity={0.85} /></mesh>
        {/* mouth — glowing arc; the group's Y-scale morphs smile↔frown↔open from the mood */}
        <group ref={mouth} position={[0, 0.54, 0.49]}>
          <mesh rotation={[Math.PI / 2, 0, Math.PI]}><torusGeometry args={[0.07, 0.016, 8, 20, Math.PI]} /><meshStandardMaterial color="#d7fbff" emissive={LED} emissiveIntensity={2} toneMapped={false} /></mesh>
        </group>

        {/* twin antennae — tip beads glow in the mood colour */}
        {[-1, 1].map((s) => (
          <group key={s}>
            <mesh position={[s * 0.22, 0.92, 0.04]} rotation={[0, 0, -s * 0.3]}>
              <cylinderGeometry args={[0.009, 0.009, 0.16, 8]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} />
            </mesh>
            <mesh position={[s * 0.27, 1.0, 0.04]}>
              <sphereGeometry args={[0.03, 12, 12]} /><meshStandardMaterial color={LED} emissive={LED} emissiveIntensity={1.4} toneMapped={false} />
            </mesh>
          </group>
        ))}

        {/* ── headphone "ear-speakers" (the music robot's ears) + mood rings ── */}
        <group position={[0, 0.62, 0]}>
          <mesh><torusGeometry args={[0.5, 0.035, 8, 24, Math.PI]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
          <mesh position={[0.5, 0, 0]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[0.13, 0.13, 0.12, 20]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
          <mesh position={[-0.5, 0, 0]} rotation={[0, 0, Math.PI / 2]}><cylinderGeometry args={[0.13, 0.13, 0.12, 20]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
          <mesh position={[0.565, 0, 0]} rotation={[0, 0, Math.PI / 2]}><torusGeometry args={[0.1, 0.018, 8, 20]} /><meshStandardMaterial color={LED} emissive={LED} emissiveIntensity={1.4} toneMapped={false} /></mesh>
          <mesh position={[-0.565, 0, 0]} rotation={[0, 0, Math.PI / 2]}><torusGeometry args={[0.1, 0.018, 8, 20]} /><meshStandardMaterial color={LED} emissive={LED} emissiveIntensity={1.4} toneMapped={false} /></mesh>
        </group>

        {/* neck collar */}
        <mesh position={[0, 0.24, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.2, 0.05, 12, 24]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
        {/* shoulder joints (round the arm/torso join; no outline, inside the silhouette) */}
        <mesh position={[-0.31, 0.13, 0]}><sphereGeometry args={[0.1, 16, 16]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
        <mesh position={[0.31, 0.13, 0]}><sphereGeometry args={[0.1, 16, 16]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>

        {/* ── rounded robot torso + glowing "music core" ── */}
        <mesh position={[0, -0.06, 0]}>
          <capsuleGeometry args={[0.27, 0.18, 10, 18]} />
          <meshToonMaterial color={SUIT} gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        {/* chest core: a mood-glowing ring + dark disc + VN gold star at its centre */}
        <mesh position={[0, 0.0, 0.255]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.1, 0.024, 12, 28]} /><meshStandardMaterial color={LED} emissive={LED} emissiveIntensity={1.6} toneMapped={false} /></mesh>
        <mesh position={[0, 0.0, 0.265]}><circleGeometry args={[0.085, 28]} /><meshStandardMaterial color={SKIN_SCREEN} emissive={LED} emissiveIntensity={0.5} /></mesh>
        <mesh position={[0, 0.0, 0.272]}><shapeGeometry args={[star]} /><meshStandardMaterial color="#d7fbff" emissive={accent} emissiveIntensity={1.4} toneMapped={false} side={DoubleSide} /></mesh>
        {/* speaker backpack with a grille */}
        <mesh position={[0, 0.0, -0.27]}>
          <boxGeometry args={[0.34, 0.34, 0.16]} />
          <meshToonMaterial color={SUIT_D} gradientMap={ramp} />
          <Outlines {...OUTLINE} />
        </mesh>
        <mesh position={[0, 0.0, -0.355]}><circleGeometry args={[0.12, 20]} /><meshStandardMaterial color="#0a0d18" emissive={LED} emissiveIntensity={0.25} /></mesh>

        {/* waist seam (neutral steel) */}
        <mesh position={[0, -0.18, 0]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[0.27, 0.025, 12, 32]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>

        {/* ── segmented robot arms: shoulder cyl → elbow joint → mitten hand ── */}
        <group ref={armL} position={[-0.31, 0.13, 0]}>
          <mesh position={[0, -0.16, 0]}><cylinderGeometry args={[0.06, 0.055, 0.22, 12]} /><meshToonMaterial color={SUIT} gradientMap={ramp} /><Outlines {...OUTLINE} /></mesh>
          <mesh position={[0, -0.28, 0]}><sphereGeometry args={[0.06, 14, 14]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
          <mesh position={[0, -0.35, 0]}><sphereGeometry args={[0.085, 16, 16]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
        </group>
        <group ref={armR} position={[0.31, 0.13, 0]}>
          <mesh position={[0, -0.16, 0]}><cylinderGeometry args={[0.06, 0.055, 0.22, 12]} /><meshToonMaterial color={SUIT} gradientMap={ramp} /><Outlines {...OUTLINE} /></mesh>
          <mesh position={[0, -0.28, 0]}><sphereGeometry args={[0.06, 14, 14]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
          <mesh position={[0, -0.35, 0]}><sphereGeometry args={[0.085, 16, 16]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
        </group>

        {/* ── robot legs: thigh → knee → shin → rounded foot (FOOT_DROP = 0.68) ── */}
        <group ref={legL} position={[-0.14, -0.28, 0]}>
          <mesh position={[0, -0.08, 0]}><cylinderGeometry args={[0.075, 0.07, 0.18, 12]} /><meshToonMaterial color={SUIT} gradientMap={ramp} /></mesh>
          <group ref={shinL} position={[0, -0.18, 0]}>
            <mesh><sphereGeometry args={[0.072, 14, 14]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
            <mesh position={[0, -0.07, 0]}><cylinderGeometry args={[0.07, 0.065, 0.16, 12]} /><meshToonMaterial color={SUIT} gradientMap={ramp} /></mesh>
            <mesh position={[0, -0.15, 0.045]} rotation={[Math.PI / 2, 0, 0]}><capsuleGeometry args={[0.07, 0.13, 6, 12]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
          </group>
        </group>
        <group ref={legR} position={[0.14, -0.28, 0]}>
          <mesh position={[0, -0.08, 0]}><cylinderGeometry args={[0.075, 0.07, 0.18, 12]} /><meshToonMaterial color={SUIT} gradientMap={ramp} /></mesh>
          <group ref={shinR} position={[0, -0.18, 0]}>
            <mesh><sphereGeometry args={[0.072, 14, 14]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
            <mesh position={[0, -0.07, 0]}><cylinderGeometry args={[0.07, 0.065, 0.16, 12]} /><meshToonMaterial color={SUIT} gradientMap={ramp} /></mesh>
            <mesh position={[0, -0.15, 0.045]} rotation={[Math.PI / 2, 0, 0]}><capsuleGeometry args={[0.07, 0.13, 6, 12]} /><meshToonMaterial color={SUIT_D} gradientMap={ramp} /></mesh>
          </group>
        </group>

        {bubble && (
          <Html center distanceFactor={6} position={[1.0, 1.2, 0]} pointerEvents="none">
            <div className="astro-speech">
              {bubble.vi}
              <span className="astro-speech-sub">{bubble.en}</span>
            </div>
          </Html>
        )}

        {/* ── music note glow sprites — animated in useFrame ── */}
        {[0, 1, 2].map((i) => (
          <sprite key={i} ref={(el) => { noteSpriteRefs.current[i] = el; }} visible={false}>
            <spriteMaterial map={tex} color="#00eeff" transparent opacity={0} blending={AdditiveBlending} depthWrite={false} />
          </sprite>
        ))}
      </group>
    </group>
  );
}
