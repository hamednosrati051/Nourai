'use client';

import { useEffect, useRef, useState } from 'react';
import { useToast } from '@/components/Toast';

/**
 * Tap-to-toggle mic recorder with a live AnalyserNode for the visualizer.
 * Calls onFile with the recorded audio file when recording stops.
 */
export function useRecorder(onFile: (file: File) => void) {
  const { toast } = useToast();
  const [recording, setRecording] = useState(false);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [recSeconds, setRecSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startingRef = useRef(false);
  const onFileRef = useRef(onFile);
  onFileRef.current = onFile;

  // Recording timer.
  useEffect(() => {
    if (recording) {
      setRecSeconds(0);
      timerRef.current = setInterval(() => setRecSeconds((s) => s + 1), 1000);
    } else if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [recording]);

  // Stop everything on unmount.
  useEffect(() => {
    return () => {
      try {
        mediaRecorderRef.current?.stop();
      } catch {
        // already stopped
      }
      audioCtxRef.current?.close().catch(() => {});
    };
  }, []);

  const beginCapture = async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream);
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' });
        if (blob.size > 0) {
          onFileRef.current(new File([blob], `recording-${Date.now()}.webm`, { type: blob.type }));
        }
      };
      rec.start();
      mediaRecorderRef.current = rec;
      // Live visualizer: analyse the mic stream.
      try {
        const AC =
          window.AudioContext ||
          (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
        const ctx = new AC();
        const src = ctx.createMediaStreamSource(stream);
        const an = ctx.createAnalyser();
        an.fftSize = 64;
        an.smoothingTimeConstant = 0.72;
        src.connect(an);
        audioCtxRef.current = ctx;
        setAnalyser(an);
      } catch {
        // Visualizer is decorative; recording works without it.
      }
      setRecording(true);
    } catch {
      toast('دسترسی به میکروفن ممکن نشد. لطفاً اجازه میکروفن را بدهید.', 'error');
    } finally {
      startingRef.current = false;
    }
  };

  const finishCapture = () => {
    try {
      mediaRecorderRef.current?.stop();
    } catch {
      // already stopped
    }
    mediaRecorderRef.current = null;
    audioCtxRef.current?.close().catch(() => {});
    audioCtxRef.current = null;
    setAnalyser(null);
  };

  const toggleRecording = () => {
    if (recording) {
      setRecording(false);
      finishCapture();
    } else {
      beginCapture();
    }
  };

  return { recording, analyser, recSeconds, toggleRecording };
}
