import { useEffect, useRef, useState } from "react";

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

/** Dictation: spoken words are appended to the answer (the student can still edit them). */
export function useDictation(language: string, append: (text: string) => void) {
  const supported = Boolean(recognitionClass());
  const [listening, setListening] = useState(false);
  const [error, setError] = useState<string>();
  const recognition = useRef<Recognition | null>(null);

  const stop = () => recognition.current?.stop();
  const start = () => {
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
    setError(undefined);
    recognition.current = r;
    r.start();
    setListening(true);
  };
  useEffect(() => () => recognition.current?.stop(), []);
  return { supported, listening, start, stop, error };
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
