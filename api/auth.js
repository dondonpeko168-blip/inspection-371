// api/auth.js — Vercel Serverless Function that redirects back to itself
// to force the rewrite chain to fire for static files.
export default async function handler(req, res) {
  const USER = process.env.BASIC_AUTH_USER;
  const PASS = process.env.BASIC_AUTH_PASS;

  const authHeader = req.headers.get('authorization');

  if (!authHeader) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('401 Unauthorized');
  }

  // Parse "Basic <base64>"
  const parts = authHeader.split(' ');
  if (parts.length !== 2) {
    return res.status(401).send('Invalid auth header');
  }
  const decoded = Buffer.from(parts[1], 'base64').toString();
  const colonIdx = decoded.indexOf(':');
  if (colonIdx === -1) {
    return res.status(401).send('Invalid auth format');
  }
  const user = decoded.substring(0, colonIdx);
  const pass = decoded.substring(colonIdx + 1);

  if (user !== USER || pass !== PASS) {
    return res.status(401).send('Invalid credentials');
  }

  // Auth succeeded — serve the original static file or API
  const forwardedPath = req.url || '/index.html';
  const origin = `https://${process.env.VERCEL_URL}`;
  const targetUrl = `${origin}${forwardedPath.startsWith('/') ? '' : '/'}${forwardedPath}`;

  try {
    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers: Object.fromEntries(
        [...req.headers.entries()].filter(([k]) => k !== 'authorization')
      ),
    });

    res.status(upstream.status);
    upstream.headers.forEach((val, key) => {
      if (key !== 'content-encoding') {
        res.setHeader(key, val);
      }
    });
    const body = await upstream.arrayBuffer();
    return res.send(Buffer.from(body));
  } catch (err) {
    return res.status(500).send('Proxy error');
  }
}