// Self-hosters opt in by setting both VITE_UMAMI_URL and VITE_UMAMI_WEBSITE_ID
// at build time. Missing either one means no script is injected — no phone-home.
const url = import.meta.env.VITE_UMAMI_URL;
const websiteId = import.meta.env.VITE_UMAMI_WEBSITE_ID;

if (url && websiteId) {
  const script = document.createElement("script");
  script.defer = true;
  script.src = url;
  script.dataset.websiteId = websiteId;
  document.head.appendChild(script);
}
