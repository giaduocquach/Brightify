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
