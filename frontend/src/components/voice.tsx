import { useEffect, useRef, useState } from "react";
import { ApiError, get, post } from "../api";

// Web Speech API: not in TypeScript's DOM types everywhere, so declare what we use.
interface RecognitionResult { isFinal: boolean; 0: { transcript: string } }
interface RecognitionEvent { resultIndex: number; results: ArrayLike<RecognitionResult> }
interface Recognition {
  lang: string; continuous: boolean; interimResults: boolean;
  start(): void; stop(): void;
  onresult: ((event: RecognitionEvent) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
}
type RecognitionCtor = new () => Recognition;

function recognitionClass(): RecognitionCtor | undefined {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

const LOCALE: Record<string, string> = { ar: "ar-SA", en: "en-US" };

interface SpeechStatus { available: boolean; engine: string; max_seconds: number }

/** Server transcription (Whisper on the university's own server) when it is running. */
function useServerSpeech() {
  const [status, setStatus] = useState<SpeechStatus | null>(null);
  useEffect(() => {
    if (typeof MediaRecorder === "undefined" || !navigator.mediaDevices) return;
    get<SpeechStatus>("speech", "/api/v1/speech/status").then(setStatus).catch(() => setStatus(null));
  }, []);
  return status?.available ? status : null;
}

/**
 * Dictation: spoken words are appended to the answer (the student can still edit them).
 * Uses the server's Whisper when available (private, better with Arabic and technical
 * terms), otherwise the browser's own speech recognition.
 */
export function useDictation(language: string, append: (text: string) => void, context?: string) {
  const server = useServerSpeech();
  const supported = Boolean(server) || Boolean(recognitionClass());
  const [listening, setListening] = useState(false);
  const [transcribing, setTranscribing] = useState(false);
  const [error, setError] = useState<string>();
  const recognition = useRef<Recognition | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const discard = useRef(false);
  const timer = useRef<number | undefined>(undefined);

  const upload = async (blob: Blob) => {
    if (!blob.size) return;
    setTranscribing(true);
    const form = new FormData();
    form.append("audio", blob, "answer.webm");
    form.append("language", language === "en" ? "en" : "ar");
    if (context) form.append("prompt", context.slice(0, 1000));
    try {
      const result = await post<{ text: string }>("speech", "/api/v1/speech/transcribe", form);
      if (result.text) append(result.text);
      else setError("لم يُفهم كلام في التسجيل، حاول مرة أخرى بصوت أوضح");
    } catch (e) {
      setError(e instanceof ApiError && e.status === 413 ? "التسجيل أطول من المسموح" : "تعذّر تحويل الصوت إلى نص؛ يمكنك الكتابة");
    } finally {
      setTranscribing(false);
    }
  };

  const startServer = async (limitSeconds: number) => {
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError("لم يُسمح باستخدام الميكروفون");
      return;
    }
    const chunks: Blob[] = [];
    const r = new MediaRecorder(stream);
    r.ondataavailable = (event) => event.data.size && chunks.push(event.data);
    r.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      window.clearTimeout(timer.current);
      setListening(false);
      if (!discard.current) void upload(new Blob(chunks, { type: r.mimeType }));
    };
    discard.current = false;
    recorder.current = r;
    r.start();
    setListening(true);
    timer.current = window.setTimeout(() => r.state === "recording" && r.stop(), limitSeconds * 1000);
  };

  const startBrowser = () => {
    const Ctor = recognitionClass();
    if (!Ctor) return;
    const r = new Ctor();
    r.lang = LOCALE[language] ?? "ar-SA";
    r.continuous = true;
    r.interimResults = false;
    r.onresult = (event) => {
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) append(event.results[i][0].transcript.trim());
      }
    };
    r.onerror = (event) => setError(event.error === "not-allowed" ? "لم يُسمح باستخدام الميكروفون" : `خطأ في التعرّف على الصوت (${event.error})`);
    r.onend = () => setListening(false);
    recognition.current = r;
    r.start();
    setListening(true);
  };

  const start = () => {
    setError(undefined);
    if (server) void startServer(server.max_seconds);
    else startBrowser();
  };
  const stop = () => {
    if (recorder.current?.state === "recording") recorder.current.stop();
    recognition.current?.stop();
  };
  /** Stop without transcribing (the answer is being sent). */
  const cancel = () => {
    discard.current = true;
    stop();
  };
  useEffect(() => () => cancel(), []); // eslint-disable-line react-hooks/exhaustive-deps
  return { supported, listening, transcribing, start, stop, cancel, error, engine: server ? "server" : "browser" };
}

export function speak(text: string, language: string) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.replace(/`/g, ""));
  utterance.lang = LOCALE[language] ?? "ar-SA";
  utterance.rate = 0.95;
  window.speechSynthesis.speak(utterance);
}

export const canSpeak = () => typeof window !== "undefined" && "speechSynthesis" in window;
