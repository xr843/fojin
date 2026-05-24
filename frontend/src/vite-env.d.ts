/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_UMAMI_URL?: string;
  readonly VITE_UMAMI_WEBSITE_ID?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Umami Analytics global
interface Window {
  umami?: {
    track: (event: string, data?: Record<string, string | number>) => void;
  };
}
declare const umami: Window["umami"];
