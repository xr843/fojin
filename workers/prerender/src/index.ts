import { isBot } from "./bot-detector";
import { renderTextPage } from "./html-renderer";
import type { TextData } from "./html-renderer";

export interface Env {
  ORIGIN: string;
  API_BASE: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const ua = request.headers.get("user-agent") || "";

    // Only intercept /texts/:id for search engine bots
    const textMatch = url.pathname.match(/^\/texts\/(\d+)$/);
    if (!textMatch || !isBot(ua)) {
      return fetch(request);
    }

    const textId = textMatch[1];

    try {
      const apiUrl = `${env.API_BASE}/texts/${textId}`;
      const apiResp = await fetch(apiUrl, {
        headers: { Accept: "application/json" },
      });

      if (!apiResp.ok) {
        // API returned an error — fall back to origin so the bot sees the
        // normal SPA shell (or a 404 from the origin).
        return fetch(request);
      }

      const textData = (await apiResp.json()) as TextData;
      const html = renderTextPage(textId, textData);

      return new Response(html, {
        status: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=86400, s-maxage=86400",
          "X-Robots-Tag": "index, follow",
          "X-Rendered-By": "fojin-prerender",
        },
      });
    } catch {
      // On any unexpected error, fall back to origin
      return fetch(request);
    }
  },
};
