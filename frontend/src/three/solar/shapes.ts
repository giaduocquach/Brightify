import { Shape } from 'three';

// A 5-point star outline — the Vietnamese gold star, reused on the astronaut's helmet +
// flag patch and on the spaceship's Đông Sơn / trống-đồng emblem.
export function starShape(outer: number, inner: number, points = 5): Shape {
  const s = new Shape();
  for (let i = 0; i < points * 2; i++) {
    const r = i % 2 ? inner : outer;
    const a = (i / (points * 2)) * Math.PI * 2 - Math.PI / 2;
    const x = Math.cos(a) * r, y = Math.sin(a) * r;
    if (i === 0) s.moveTo(x, y); else s.lineTo(x, y);
  }
  s.closePath();
  return s;
}
