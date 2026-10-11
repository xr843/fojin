import { Navigate, useLocation } from "react-router";

/**
 * Permanent in-app redirect that carries the query string and hash along.
 *
 * A bare `<Navigate to="/x" replace />` drops `?lang=en`, so a retired route
 * reached through a stale in-app link or an old PWA shell would land on the
 * new page in the wrong language variant. nginx does the real 301 for
 * crawlers (`return 301 /x$is_args$args`); this is the client-side mirror.
 */
export default function RedirectKeepingSearch({ to }: { to: string }) {
  const { search, hash } = useLocation();
  return <Navigate to={{ pathname: to, search, hash }} replace />;
}
