// MWaves - YouTube Audio Visualizer Content Script
// Glass bars + smooth framerate-independent motion

let audioContext;
let analyser;
let source;
let canvas;
let canvasCtx;
let animationId;
let isEnabled = true;
let visualizerStyle = 'bars';
let isSymmetric = false;
let maxHeightFactor = 0.4;
let visualBarCount = 64;
let videoElement;
let colorCanvas;
let colorCtx;
let currentColor = { r: 255, g: 255, b: 255 };
let targetColor = { r: 255, g: 255, b: 255 };
let bars = [];
let glowIntensity = 15;

let prevMagnitudes = null;
let spectralFlux = 0;
let smoothedFlux = 0;

let shockwaves = [];
let lastShockwaveTime = 0;

let currentRMS = 0;
let peakTracker = 1.0;
let corsFailed = false;
let resizeObserver = null;
let lastFrameTime = performance.now();
let forceOverride = null; // null = auto-detect, true = forced on via toggle button

class Bar {
    constructor(index, totalBars) {
        this.smoothedValue = 0;
        this.index = index;
        this.freqRatio = totalBars > 0 ? index / totalBars : 0;
        const ratio = this.freqRatio;
        if (ratio < 0.5) {
            this.decayAlpha = 0.08 + (ratio / 0.5) * 0.10;
        } else {
            this.decayAlpha = 0.18 - ((ratio - 0.5) / 0.5) * 0.06;
        }
    }

    update(rawValue, flux, dt) {
        const attackAlpha60fps = 0.35 + Math.min(0.45, flux * 2.0);
        const alpha60fps = rawValue > this.smoothedValue ? attackAlpha60fps 