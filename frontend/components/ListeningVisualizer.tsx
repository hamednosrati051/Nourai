'use client';

import { useEffect, useRef } from 'react';

/** Live listening visualizer: gradient bars driven by the real mic level. */
export function ListeningVisualizer({ analyser }: { analyser: AnalyserNode }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    const N = 28;
    let raf = 0;

    const draw = () => {
      raf = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(data);
      const w = canvas.width;
      const h = canvas.height;
      ctx.clearRect(0, 0, w, h);
      const gap = 6;
      const bw = (w - gap * (N - 1)) / N;
      const grad = ctx.createLinearGradient(0, h, 0, 0);
      grad.addColorStop(0, '#f59e0b');
      grad.addColorStop(1, '#ec4899');
      ctx.fillStyle = grad;
      for (let i = 0; i < N; i++) {
        // favour lower (voice) frequencies
        const v = (data[Math.floor((i / N) * data.length * 0.7)] ?? 0) / 255;
        const bh = Math.max(6, v * h);
        const x = i * (bw + gap);
        const y = (h - bh) / 2;
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') ctx.roundRect(x, y, bw, bh, bw / 2);
        else ctx.rect(x, y, bw, bh);
        ctx.fill();
      }
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [analyser]);

  return <canvas ref={canvasRef} width={520} height={96} className="h-12 w-64" />;
}
