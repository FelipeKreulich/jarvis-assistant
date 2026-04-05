from PyQt6.QtCore import QUrl, pyqtSlot
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings


ORB_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin: 0; padding: 0; }
  body { background: #050810; overflow: hidden; }
  canvas { display: block; }
</style>
</head>
<body>
<canvas id="c"></canvas>
<script>
const canvas = document.getElementById('c');
const ctx = canvas.getContext('2d');

let W, H, cx, cy, baseR;
function resize() {
  W = canvas.width = window.innerWidth;
  H = canvas.height = window.innerHeight;
  cx = W / 2;
  cy = H / 2;
  baseR = Math.min(W, H) * 0.22;
}
resize();
window.addEventListener('resize', resize);

// State management
let state = 'idle';       // idle, listening, thinking, speaking, error
let amplitude = 0;        // 0-1, mic or tts amplitude
let targetAmplitude = 0;
let stateTime = 0;        // time since state change
let prevState = 'idle';
let transitionProgress = 1; // 0-1
const TRANSITION_DURATION = 600; // ms

// Particles
const particles = [];
const NUM_PARTICLES = 60;
for (let i = 0; i < NUM_PARTICLES; i++) {
  particles.push({
    angle: Math.random() * Math.PI * 2,
    radius: 1.3 + Math.random() * 0.5,
    speed: (0.15 + Math.random() * 0.3) * (Math.random() > 0.5 ? 1 : -1),
    size: 1 + Math.random() * 2,
    opacity: 0.3 + Math.random() * 0.5,
    phase: Math.random() * Math.PI * 2,
  });
}

// Ripples (for listening state)
const ripples = [];
function addRipple(intensity) {
  ripples.push({ radius: 0, opacity: 0.3 + intensity * 0.4, speed: 1 + intensity * 2, born: performance.now() });
  if (ripples.length > 8) ripples.shift();
}

// Halos (for speaking state)
const halos = [];
function addHalo() {
  halos.push({ radius: 0, opacity: 0.25, born: performance.now() });
  if (halos.length > 5) halos.shift();
}

let lastRippleTime = 0;
let lastHaloTime = 0;

// Color palettes per state
const palettes = {
  idle:      { core: [8, 15, 40],    mid: [20, 80, 180],   glow: [60, 140, 255],  outer: [120, 80, 200] },
  listening: { core: [10, 25, 50],    mid: [40, 160, 220],  glow: [140, 230, 255], outer: [80, 200, 255] },
  thinking:  { core: [20, 8, 40],     mid: [80, 40, 160],   glow: [140, 80, 220],  outer: [180, 100, 255] },
  speaking:  { core: [15, 25, 50],    mid: [60, 140, 220],  glow: [180, 210, 255], outer: [140, 180, 255] },
  error:     { core: [50, 10, 5],     mid: [200, 60, 20],   glow: [255, 120, 40],  outer: [255, 80, 30]  },
};

function lerpColor(a, b, t) {
  return a.map((v, i) => Math.round(v + (b[i] - v) * t));
}

function getColors(t) {
  const p1 = palettes[prevState] || palettes.idle;
  const p2 = palettes[state] || palettes.idle;
  const ease = easeInOut(transitionProgress);
  return {
    core: lerpColor(p1.core, p2.core, ease),
    mid:  lerpColor(p1.mid, p2.mid, ease),
    glow: lerpColor(p1.glow, p2.glow, ease),
    outer: lerpColor(p1.outer, p2.outer, ease),
  };
}

function easeInOut(t) {
  return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
}

// Noise function for organic movement
function noise(x, y) {
  const s = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453;
  return s - Math.floor(s);
}

function smoothNoise(t, seed) {
  return Math.sin(t * 1.1 + seed) * 0.5
       + Math.sin(t * 2.3 + seed * 1.7) * 0.25
       + Math.sin(t * 4.1 + seed * 0.3) * 0.125;
}

let time = 0;
let lastFrame = performance.now();

function draw(now) {
  const dt = (now - lastFrame) / 1000;
  lastFrame = now;
  time += dt;

  // Transition progress
  if (transitionProgress < 1) {
    transitionProgress = Math.min(1, transitionProgress + dt * 1000 / TRANSITION_DURATION);
  }

  // Smooth amplitude
  amplitude += (targetAmplitude - amplitude) * Math.min(1, dt * 12);

  ctx.clearRect(0, 0, W, H);
  ctx.save();

  const colors = getColors(time);

  // Compute dynamic radius
  let r = baseR;
  if (state === 'idle') {
    r *= 0.95 + 0.1 * Math.sin(time * 2.1) * 0.5 + 0.05;
  } else if (state === 'listening') {
    r *= 1.0 + amplitude * 0.25 + smoothNoise(time * 3, 1) * 0.03;
    if (now - lastRippleTime > 120 && amplitude > 0.15) {
      addRipple(amplitude);
      lastRippleTime = now;
    }
  } else if (state === 'thinking') {
    r *= 0.95 + 0.05 * Math.sin(time * 4);
  } else if (state === 'speaking') {
    r *= 1.0 + amplitude * 0.15 + Math.sin(time * 5) * 0.03;
    if (now - lastHaloTime > 800) {
      addHalo();
      lastHaloTime = now;
    }
  } else if (state === 'error') {
    r *= 1.0 + 0.05 * Math.sin(time * 20) * Math.max(0, 1 - stateTime / 500);
  }
  stateTime += dt * 1000;

  // === Outer glow ===
  const outerGlow = ctx.createRadialGradient(cx, cy, r * 0.8, cx, cy, r * 2.2);
  outerGlow.addColorStop(0, `rgba(${colors.outer.join(',')}, 0.08)`);
  outerGlow.addColorStop(0.5, `rgba(${colors.outer.join(',')}, 0.03)`);
  outerGlow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = outerGlow;
  ctx.fillRect(0, 0, W, H);

  // === Halos (speaking) ===
  for (let i = halos.length - 1; i >= 0; i--) {
    const h = halos[i];
    const age = (now - h.born) / 1000;
    const haloR = r + age * baseR * 0.8;
    const opacity = h.opacity * Math.max(0, 1 - age / 2.5);
    if (opacity <= 0) { halos.splice(i, 1); continue; }
    ctx.beginPath();
    ctx.arc(cx, cy, haloR, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${colors.glow.join(',')}, ${opacity * 0.4})`;
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  // === Ripples (listening) ===
  for (let i = ripples.length - 1; i >= 0; i--) {
    const rp = ripples[i];
    const age = (now - rp.born) / 1000;
    const ripR = r + age * baseR * 1.2;
    const opacity = rp.opacity * Math.max(0, 1 - age / 1.5);
    if (opacity <= 0) { ripples.splice(i, 1); continue; }
    ctx.beginPath();
    ctx.arc(cx, cy, ripR, 0, Math.PI * 2);
    ctx.strokeStyle = `rgba(${colors.glow.join(',')}, ${opacity * 0.5})`;
    ctx.lineWidth = 1.5 + (1 - age / 1.5) * 2;
    ctx.stroke();
  }

  // === Outer ring ===
  const ringSpeed = state === 'listening' ? 0.5 : state === 'thinking' ? 0.8 : 0.15;
  const ringR = r * 1.15;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(time * ringSpeed);
  const ringSegments = 40;
  for (let i = 0; i < ringSegments; i++) {
    const a = (i / ringSegments) * Math.PI * 2;
    const osc = 0.5 + 0.5 * Math.sin(a * 3 + time * 2);
    const segR = ringR + smoothNoise(time + i, 5) * r * 0.05;
    const px = Math.cos(a) * segR;
    const py = Math.sin(a) * segR;
    ctx.beginPath();
    ctx.arc(px, py, 1 + osc * 1.5, 0, Math.PI * 2);
    ctx.fillStyle = `rgba(${colors.glow.join(',')}, ${0.15 + osc * 0.25})`;
    ctx.fill();
  }
  ctx.restore();

  // === Thinking loading arc ===
  if (state === 'thinking' || (prevState === 'thinking' && transitionProgress < 1)) {
    const arcOpacity = state === 'thinking' ? easeInOut(Math.min(1, stateTime / 400)) : 1 - easeInOut(transitionProgress);
    ctx.save();
    ctx.translate(cx, cy);
    const arcAngle = time * 3;
    ctx.beginPath();
    ctx.arc(0, 0, r * 1.22, arcAngle, arcAngle + Math.PI * 0.6);
    ctx.strokeStyle = `rgba(${colors.glow.join(',')}, ${arcOpacity * 0.6})`;
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.stroke();
    // Second arc opposite
    ctx.beginPath();
    ctx.arc(0, 0, r * 1.22, arcAngle + Math.PI, arcAngle + Math.PI + Math.PI * 0.4);
    ctx.strokeStyle = `rgba(${colors.outer.join(',')}, ${arcOpacity * 0.4})`;
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.restore();
  }

  // === Main orb layers ===
  // Layer 1: deep core
  const coreGrad = ctx.createRadialGradient(cx, cy - r * 0.15, 0, cx, cy, r);
  coreGrad.addColorStop(0, `rgba(${colors.core.map(c => c + 30).join(',')}, 1)`);
  coreGrad.addColorStop(0.5, `rgba(${colors.core.join(',')}, 0.95)`);
  coreGrad.addColorStop(1, `rgba(${colors.core.join(',')}, 0.3)`);
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = coreGrad;
  ctx.fill();

  // Layer 2: mid energy layer with distortion
  ctx.save();
  ctx.globalCompositeOperation = 'screen';
  const midGrad = ctx.createRadialGradient(cx, cy, r * 0.1, cx, cy, r * 0.85);
  const midAlpha = 0.3 + (state === 'listening' ? amplitude * 0.3 : 0) + (state === 'speaking' ? amplitude * 0.2 : 0);
  midGrad.addColorStop(0, `rgba(${colors.mid.join(',')}, ${midAlpha})`);
  midGrad.addColorStop(0.6, `rgba(${colors.mid.join(',')}, ${midAlpha * 0.5})`);
  midGrad.addColorStop(1, `rgba(${colors.mid.join(',')}, 0)`);
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.85, 0, Math.PI * 2);
  ctx.fillStyle = midGrad;
  ctx.fill();
  ctx.restore();

  // Layer 3: inner glow pulse
  const pulseIntensity = state === 'idle' ? 0.3 + 0.2 * Math.sin(time * 2.5)
    : state === 'listening' ? 0.4 + amplitude * 0.5
    : state === 'thinking' ? 0.3 + 0.3 * Math.sin(time * 5)
    : state === 'speaking' ? 0.4 + amplitude * 0.4
    : 0.8;
  ctx.save();
  ctx.globalCompositeOperation = 'screen';
  const innerGlow = ctx.createRadialGradient(cx, cy - r * 0.1, 0, cx, cy, r * 0.7);
  innerGlow.addColorStop(0, `rgba(${colors.glow.join(',')}, ${pulseIntensity * 0.6})`);
  innerGlow.addColorStop(0.4, `rgba(${colors.glow.join(',')}, ${pulseIntensity * 0.2})`);
  innerGlow.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.beginPath();
  ctx.arc(cx, cy, r * 0.7, 0, Math.PI * 2);
  ctx.fillStyle = innerGlow;
  ctx.fill();
  ctx.restore();

  // Layer 4: swirling energy lines (more active in thinking)
  ctx.save();
  ctx.globalCompositeOperation = 'screen';
  const numSwirls = 5;
  const swirlSpeed = state === 'thinking' ? 2.5 : state === 'listening' ? 1.0 : 0.4;
  for (let s = 0; s < numSwirls; s++) {
    ctx.beginPath();
    const swirlPhase = (s / numSwirls) * Math.PI * 2;
    for (let j = 0; j <= 60; j++) {
      const t2 = j / 60;
      const angle = swirlPhase + t2 * Math.PI * 3 + time * swirlSpeed;
      const swirlR = t2 * r * 0.85;
      const x = cx + Math.cos(angle) * swirlR;
      const y = cy + Math.sin(angle) * swirlR;
      if (j === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.strokeStyle = `rgba(${colors.glow.join(',')}, ${0.05 + (state === 'thinking' ? 0.08 : 0.02)})`;
    ctx.lineWidth = 1.5;
    ctx.stroke();
  }
  ctx.restore();

  // Layer 5: specular highlight (3D look)
  const specGrad = ctx.createRadialGradient(cx - r * 0.25, cy - r * 0.3, 0, cx, cy, r);
  specGrad.addColorStop(0, 'rgba(200, 220, 255, 0.12)');
  specGrad.addColorStop(0.3, 'rgba(200, 220, 255, 0.04)');
  specGrad.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fillStyle = specGrad;
  ctx.fill();

  // Layer 6: rim light
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(${colors.glow.join(',')}, 0.15)`;
  ctx.lineWidth = 1.5;
  ctx.stroke();
  ctx.restore();

  // === Orbiting particles ===
  ctx.save();
  for (const p of particles) {
    p.angle += p.speed * dt;
    const wobble = smoothNoise(time * 0.5, p.phase) * 0.1;
    const pR = r * (p.radius + wobble);
    const px = cx + Math.cos(p.angle) * pR;
    const py = cy + Math.sin(p.angle) * pR;
    const pop = 0.5 + 0.5 * Math.sin(time * 2 + p.phase);
    const pSize = p.size * (0.8 + pop * 0.4);
    const pAlpha = p.opacity * (0.5 + pop * 0.5);

    const pGrad = ctx.createRadialGradient(px, py, 0, px, py, pSize * 2);
    pGrad.addColorStop(0, `rgba(${colors.glow.join(',')}, ${pAlpha})`);
    pGrad.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.beginPath();
    ctx.arc(px, py, pSize * 2, 0, Math.PI * 2);
    ctx.fillStyle = pGrad;
    ctx.fill();
  }
  ctx.restore();

  ctx.restore();
  requestAnimationFrame(draw);
}

requestAnimationFrame(draw);

// API exposed to Python
window.setState = function(newState) {
  if (newState !== state) {
    prevState = state;
    state = newState;
    transitionProgress = 0;
    stateTime = 0;
  }
};

window.setAmplitude = function(amp) {
  targetAmplitude = amp;
};
</script>
</body>
</html>
"""


class OrbWidget(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: #050810;")
        self.page().setBackgroundColor(self.palette().color(self.backgroundRole()))

        settings = self.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.ShowScrollBars, False)

        self.setHtml(ORB_HTML, QUrl("about:blank"))

    @pyqtSlot(str)
    def set_state(self, state: str):
        self.page().runJavaScript(f"window.setState('{state}');")

    @pyqtSlot(float)
    def set_amplitude(self, amp: float):
        self.page().runJavaScript(f"window.setAmplitude({amp});")
