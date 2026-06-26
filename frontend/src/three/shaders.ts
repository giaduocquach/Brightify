// GLSL building blocks shared by the skydome and the morphing mood core.

export const SIMPLEX = /* glsl */ `
vec3 mod289v3(vec3 x){return x-floor(x*(1./289.))*289.;}
vec4 mod289v4(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 permute(vec4 x){return mod289v4(((x*34.)+1.)*x);}
vec4 taylorInvSqrt(vec4 r){return 1.79284291400159-.85373472095314*r;}
float snoise(vec3 v){
  const vec2 C=vec2(1./6.,1./3.); const vec4 D=vec4(0.,.5,1.,2.);
  vec3 i=floor(v+dot(v,C.yyy)); vec3 x0=v-i+dot(i,C.xxx);
  vec3 g=step(x0.yzx,x0.xyz); vec3 l=1.-g;
  vec3 i1=min(g.xyz,l.zxy); vec3 i2=max(g.xyz,l.zxy);
  vec3 x1=x0-i1+C.xxx; vec3 x2=x0-i2+C.yyy; vec3 x3=x0-D.yyy;
  i=mod289v3(i);
  vec4 p=permute(permute(permute(
    i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
  float n_=.142857142857; vec3 ns=n_*D.wyz-D.xzx;
  vec4 j=p-49.*floor(p*ns.z*ns.z);
  vec4 x_=floor(j*ns.z); vec4 y_=floor(j-7.*x_);
  vec4 x=x_*ns.x+ns.yyyy; vec4 y=y_*ns.x+ns.yyyy; vec4 h=1.-abs(x)-abs(y);
  vec4 b0=vec4(x.xy,y.xy); vec4 b1=vec4(x.zw,y.zw);
  vec4 s0=floor(b0)*2.+1.; vec4 s1=floor(b1)*2.+1.; vec4 sh=-step(h,vec4(0.));
  vec4 a0=b0.xzyw+s0.xzyw*sh.xxyy; vec4 a1=b1.xzyw+s1.xzyw*sh.zzww;
  vec3 p0=vec3(a0.xy,h.x); vec3 p1=vec3(a0.zw,h.y);
  vec3 p2=vec3(a1.xy,h.z); vec3 p3=vec3(a1.zw,h.w);
  vec4 norm=taylorInvSqrt(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));
  p0*=norm.x;p1*=norm.y;p2*=norm.z;p3*=norm.w;
  vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.); m=m*m;
  return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));
}`;

// Fresnel rim used for the emotion-coloured planetary atmosphere shell: a slightly
// larger sphere whose edges glow in the body's emotion hue, so a photoreal planet
// still reads as its colour.
export const ATMO_VERT = /* glsl */ `
varying vec3 vNormal; varying vec3 vView;
void main(){
  vNormal = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vView = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;

export const ATMO_FRAG = /* glsl */ `
uniform vec3 uColor; uniform float uIntensity; uniform float uPower;
varying vec3 vNormal; varying vec3 vView;
void main(){
  float fres = pow(1.0 - max(dot(vNormal, vView), 0.0), uPower);
  gl_FragColor = vec4(uColor, fres * uIntensity);
}`;

// Subtle gas-giant detail shell for Uranus/Neptune — a thin additive sphere over the textured
// planet adding faint latitudinal BANDS, faint cloud STREAKS, and a soft limb haze, so the
// near-featureless ice giants read as real atmospheres instead of flat single-colour discs.
// vLat = object-space latitude (spin about Y preserves it); reuse SIMPLEX.
export const GIANT_VERT = /* glsl */ `
varying float vLat;
varying vec3 vNormalV;
varying vec3 vViewV;
varying vec3 vDir;
void main(){
  vLat = normalize(normal).y;
  vDir = normalize(position);
  vNormalV = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vViewV = normalize(-mv.xyz);
  gl_Position = projectionMatrix * mv;
}`;

export const GIANT_FRAG = /* glsl */ `
${SIMPLEX}
uniform float uTime, uBandStrength, uBandFreq, uStreakStrength, uOpacity;
uniform vec3 uTint;
varying float vLat;
varying vec3 vNormalV;
varying vec3 vViewV;
varying vec3 vDir;
void main(){
  float band = sin(vLat * uBandFreq + snoise(vec3(0.0, vLat * 3.0, uTime * 0.02)) * 0.6) * 0.5 + 0.5;
  float streak = snoise(vDir * 4.0 + vec3(0.0, 0.0, uTime * 0.03)) * 0.5 + 0.5;
  float fres = pow(1.0 - max(dot(vNormalV, vViewV), 0.0), 3.0);  // limb haze
  float intensity = uOpacity * (band * uBandStrength * 8.0 + streak * uStreakStrength * 6.0 + fres * 0.35);
  gl_FragColor = vec4(uTint, clamp(intensity, 0.0, 0.6));
}`;

// Vibe grade — a cheap screen-space colour grade (postprocessing Effect form) that makes the
// WHOLE cosmos take on the now-playing song's valence-arousal mood: desaturate toward luma for
// sad/low moods (uSat<1), multiply by a mood tint (warm for happy, cool indigo for sad), and a
// gentle beat-synced lift on bright areas. uTint≈white + uSat≈1 → near-passthrough. One dependent
// read, no convolution → merges with Bloom/SMAA for ~free.
export const VIBE_GRADE_FRAG = /* glsl */ `
uniform vec3 uTint; uniform float uSat; uniform float uBeat;
void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor){
  vec3 c = inputColor.rgb;
  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
  c = mix(vec3(l), c, uSat);            // desaturate toward luma (sad moods)
  c *= uTint;                            // mood tint (warm ↔ cool)
  c += uTint * l * uBeat * 0.12;         // gentle beat lift on already-bright pixels
  outputColor = vec4(c, inputColor.a);
}`;

// Aurora curtains for calm/happy moods (Q1/Q4) — large additive planes high over the scene with
// FBM-driven vertical "curtains" that scroll and fade top/bottom. uOpacity gates the whole thing
// (0 = invisible) so it can ramp in/out with the vibe weight. Reuses SIMPLEX.
export const AURORA_VERT = /* glsl */ `
varying vec2 vUv;
void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0); }`;

export const AURORA_FRAG = /* glsl */ `
${SIMPLEX}
uniform float uTime, uOpacity, uShimmer;
uniform vec3 uColA, uColB;
varying vec2 vUv;
float fbm(vec3 p){ float s = 0.0, a = 0.5; for(int i = 0; i < 3; i++){ s += a * snoise(p); p *= 2.0; a *= 0.5; } return s; }
void main(){
  float n = fbm(vec3(vUv.x * 3.0, vUv.y * 1.5 - uTime * 0.15 * uShimmer, uTime * 0.05));
  float curtain = smoothstep(0.2, 0.92, 0.5 + 0.5 * sin(vUv.x * 16.0 + n * 3.2));
  float vfade = smoothstep(0.0, 0.35, vUv.y) * (1.0 - smoothstep(0.6, 1.0, vUv.y));
  vec3 col = mix(uColA, uColB, clamp(vUv.y + n * 0.2, 0.0, 1.0));
  gl_FragColor = vec4(col, curtain * vfade * uOpacity);
}`;

// Twinkling coloured stars (round soft points). Each star has a deterministic phase + size so
// it shimmers subtly (very low amplitude — real space doesn't atmospherically twinkle, this is
// just for "alive"), with a few bright "hero" stars. Uses the geometry's `color` attribute.
export const STAR_VERT = /* glsl */ `
attribute vec3 color;
attribute float aPhase;
attribute float aSize;
uniform float uTime, uPixelRatio, uTwinkle;
varying vec3 vCol;
void main(){
  // uTwinkle (mood, ~0.6 calm … ~2.5 upbeat) scales the shimmer amplitude + a brightness lift
  float tw = 0.85 + 0.15 * uTwinkle * sin(uTime * 1.5 + aPhase);
  vCol = color * tw * (0.9 + 0.25 * (uTwinkle - 1.0));
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  gl_Position = projectionMatrix * mv;
  gl_PointSize = aSize * uPixelRatio * (300.0 / max(-mv.z, 0.1));
}`;

export const STAR_FRAG = /* glsl */ `
varying vec3 vCol;
void main(){
  float d = length(gl_PointCoord - 0.5);
  float a = 1.0 - smoothstep(0.35, 0.5, d);
  if (a < 0.01) discard;
  gl_FragColor = vec4(vCol, a);
}`;
