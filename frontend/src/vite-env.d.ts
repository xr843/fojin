/// <reference types="vite/client" />

// Umami Analytics global
interface Window {
  umami?: {
    track: (event: string, data?: Record<string, string | number>) => void;
  };
}
declare const umami: Window["umami"];
