// Fixed-origin proxy: never accept an upstream URL from a client.
const ORIGIN = 'https://p01--mc-killer--78ddxkxpby92.code.run';
export default {
  async fetch(request) {
    const publicUrl = new URL(request.url);
    const upstream = new URL(ORIGIN);
    upstream.pathname = publicUrl.pathname;
    upstream.search = publicUrl.search;
    const headers = new Headers(request.headers);
    headers.delete('host');
    headers.delete('forwarded');
    headers.delete('x-forwarded-for');
    headers.set('x-forwarded-host', publicUrl.host);
    headers.set('x-forwarded-proto', 'https');
    try {
      const response = await fetch(new Request(upstream, {
        method: request.method, headers,
        body: ['GET', 'HEAD'].includes(request.method) ? undefined : request.body,
        redirect: 'manual',
      }), { cf: { cacheTtl: 0, cacheEverything: false } });
      const outgoing = new Headers(response.headers);
      outgoing.set('Cache-Control', 'no-store');
      const location = outgoing.get('Location');
      if (location) {
        const target = new URL(location, upstream);
        if (target.origin === ORIGIN) {
          target.host = publicUrl.host;
          target.protocol = 'https:';
          outgoing.set('Location', target.href);
        }
      }
      return new Response(response.body, {status: response.status, headers: outgoing});
    } catch {
      return new Response('MC-Killer backend is temporarily unavailable. Please try again shortly.', {
        status: 502, headers: {'Content-Type': 'text/plain; charset=utf-8', 'Cache-Control': 'no-store'},
      });
    }
  },
};
