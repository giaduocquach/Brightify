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

export const SKY_VERT = /* glsl */ `
varying vec3 vDir;
void main(){ vDir = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`;

export const SKY_FRAG = /* glsl */ `
${SIMPLEX}
uniform float uTime; uniform float uRms;
uniform vec3 uTop; uniform vec3 uBot;
varying vec3 vDir;
void main(){
  vec3 d = normalize(vDir);
  float t = clamp(d.y*0.5+0.5, 0., 1.);
  float n = snoise(d*1.7 + uTime*0.025) * 0.07;
  vec3 col = mix(uBot, uTop, smoothstep(0.0, 1.0, t + n));
  col *= 0.85 + uRms*0.5;          // brighten with energy
  gl_FragColor = vec4(col, 1.0);
}`;

export const CORE_VERT = /* glsl */ `
${SIMPLEX}
uniform float uTime; uniform float uArousal; uniform float uRms;
varying float vN; varying vec3 vNormal;
void main(){
  float n = snoise(position*1.1 + uTime*0.12);
  float n2 = snoise(position*2.3 - uTime*0.07)*0.4;
  vN = n+n2; vNormal = normalize(normalMatrix*normal);
  float disp = vN*0.28*(0.4+uArousal*0.6) + uRms*0.2;
  gl_Position = projectionMatrix*modelViewMatrix*vec4(position+normal*disp,1.);
}`;

export const CORE_FRAG = /* glsl */ `
uniform vec3 uColA; uniform vec3 uColB; uniform float uAlpha;
varying float vN; varying vec3 vNormal;
void main(){
  float t = vN*0.5+0.5;
  vec3 col = mix(uColA, uColB, t);
  float light = dot(vNormal, normalize(vec3(.8,.6,1.)))*0.35+0.65;
  gl_FragColor = vec4(col*light, uAlpha*(0.7+t*0.3));
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

// Accretion disk for the black hole: a flat RingGeometry (XY plane) shaded entirely in the
// fragment stage. fbm noise in a sheared polar space gives swirling filaments that rotate
// faster on the inside (differential rotation); a hot-inner→cool-outer ramp + a one-sided
// Doppler brightening sell a real accretion disk. No raymarching / lensing → cheap.
export const DISK_VERT = /* glsl */ `
varying vec2 vPos;
void main(){
  vPos = position.xy;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}`;

export const DISK_FRAG = /* glsl */ `
${SIMPLEX}
uniform float uTime, uInner, uOuter, uInnerSpeed, uOuterSpeed, uDoppler, uDopplerDir, uSelected;
uniform vec3 uColHot, uColMid, uColOuter;
varying vec2 vPos;
float fbm(vec3 p){ float s = 0.0, a = 0.5; for(int i = 0; i < 4; i++){ s += a * snoise(p); p *= 2.0; a *= 0.5; } return s; }
void main(){
  float r = length(vPos);
  float rn = clamp((r - uInner) / (uOuter - uInner), 0.0, 1.0);
  float theta = atan(vPos.y, vPos.x);
  float ang = theta + uTime * mix(uInnerSpeed, uOuterSpeed, rn); // inner spins faster
  vec2 sw = vec2(cos(ang), sin(ang)) * (1.0 + rn * 3.0);         // seam-free polar sample
  float n = fbm(vec3(sw, uTime * 0.05 + rn * 2.0));
  float fil = clamp(0.5 + 0.6 * n, 0.0, 1.0);
  vec3 col = rn < 0.5 ? mix(uColHot, uColMid, rn * 2.0)
                      : mix(uColMid, uColOuter, (rn - 0.5) * 2.0);
  float dop = 1.0 + uDoppler * cos(theta - uDopplerDir);         // one limb brighter
  float hot = mix(1.9, 0.6, rn);                                 // inner edge blooms
  float bright = fil * dop * hot * (1.0 + uSelected * 0.4);
  float edge = smoothstep(0.0, 0.07, rn) * (1.0 - smoothstep(0.8, 1.0, rn));
  float a = edge * (0.35 + 0.65 * fil);
  gl_FragColor = vec4(col * bright, a);
}`;

// Screen-space gravitational lensing for the black hole (postprocessing Effect form;
// `aspect` is provided by the EffectMaterial). `mainUv` bends the sampling UV radially around
// the hole's screen position (a single dependent read → NOT a convolution, so it merges with
// Bloom/SMAA) so the background warps around it; `mainImage` then darkens a void at the core
// and adds a bright Einstein/photon ring on the already-sampled colour. THIS is what makes it
// read as a HOLE bending space, not a black ball. uStrength=0 → passthrough (off-screen/far).
export const LENS_FRAG = /* glsl */ `
uniform vec2 uLensPos;
uniform float uLensRadius;
uniform float uStrength;
void mainUv(inout vec2 uv){
  if (uStrength < 0.001) return;
  vec2 asp = vec2(aspect, 1.0);
  vec2 d = (uv - uLensPos) * asp;                    // circularize (aspect-corrected)
  float dist = length(d);
  float R = uLensRadius;
  float bend = uStrength * R / max(dist, R * 0.35);  // ∝ 1/dist deflection
  bend *= 1.0 - smoothstep(R * 3.0, R * 5.0, dist);  // taper to 0 far out
  uv -= (d / max(dist, 1e-4) / asp) * bend * 0.06;   // pull background inward around the hole
}
void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor){
  if (uStrength < 0.001) { outputColor = inputColor; return; }
  vec2 asp = vec2(aspect, 1.0);
  vec2 d = (uv - uLensPos) * asp;
  float dist = length(d);
  float R = uLensRadius;
  float shadow = smoothstep(R * 0.62, R * 0.42, dist);          // dark void at the core
  float ring = exp(-pow((dist - R * 0.85) / (R * 0.10), 2.0));  // thin Einstein ring
  vec3 ringCol = vec3(1.0, 0.92, 0.78) * ring * uStrength * 1.4;
  vec3 col = mix(inputColor.rgb, vec3(0.0), shadow) + ringCol;
  outputColor = vec4(col, inputColor.a);
}`;

// Comet tail as a GPU particle cloud (THREE.Points). Each particle streams along local +Y
// (the tail group already aims +Y anti-sunward) with age `t`, widening + a deterministic
// wobble + an optional sideways curve (dust tail). Fades and shrinks with age → a living,
// vivid tail instead of a flat cone. Cheap: only uTime updates per frame.
export const COMET_TAIL_VERT = /* glsl */ `
attribute float aSeed;
attribute float aLength01;
uniform float uTime, uLen, uSpeed, uWidth, uCurve, uSize, uPixelRatio;
varying float vAge;
void main(){
  float t = fract(aLength01 + uTime * uSpeed * (0.6 + aSeed * 0.8)); // 0=head → 1=tip
  float ang = aSeed * 6.2831853;
  float wob = sin(aSeed * 12.0 + t * 9.0 + uTime * 1.5) * uWidth * 0.4 * t;
  vec3 pos;
  pos.x = cos(ang) * uWidth * (0.15 + t) + wob + uCurve * t * t * uLen;
  pos.z = sin(ang) * uWidth * (0.15 + t);
  pos.y = t * uLen;
  vec4 mv = modelViewMatrix * vec4(pos, 1.0);
  gl_Position = projectionMatrix * mv;
  vAge = t;
  gl_PointSize = uSize * uPixelRatio * (1.0 - t * 0.5) * (260.0 / max(-mv.z, 0.1));
}`;

export const COMET_TAIL_FRAG = /* glsl */ `
uniform sampler2D uTex;
uniform vec3 uColNear, uColFar;
uniform float uOpacity;
varying float vAge;
void main(){
  float a = texture2D(uTex, gl_PointCoord).a;
  vec3 col = mix(uColNear, uColFar, vAge);
  gl_FragColor = vec4(col, a * (1.0 - vAge) * uOpacity);
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

// Twinkling coloured stars (round soft points). Each star has a deterministic phase + size so
// it shimmers subtly (very low amplitude — real space doesn't atmospherically twinkle, this is
// just for "alive"), with a few bright "hero" stars. Uses the geometry's `color` attribute.
export const STAR_VERT = /* glsl */ `
attribute vec3 color;
attribute float aPhase;
attribute float aSize;
uniform float uTime, uPixelRatio;
varying vec3 vCol;
void main(){
  float tw = 0.85 + 0.15 * sin(uTime * 1.5 + aPhase);
  vCol = color * tw;
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
