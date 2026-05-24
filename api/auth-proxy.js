const { Buffer } = require('node:buffer');

// Environment variables – set in Vercel Dashboard (already added)
const USER = process.env.BASIC_AUTH_USER;
const PASS = process.env.BASIC_AUTH_PASS;

module.exports = async (req, res) => {
  // 1️⃣ Read Authorization header
  const authHeader = req.headers.get('authorization');
  if (!authHeader) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Authentication required');
  }

  // 2️⃣ Parse "Basic <base64>"
  const [, encoded] = authHeader.split(' ') ?? [];
  if (!encoded) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid authentication header');
  }
  const decoded = Buffer.from(encoded, 'base64').toString();
  const [user, pass] = decoded.split(':');

  // 3️⃣ Verify credentials
  if (user !== USER || pass !== PASS) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid credentials');
  }

  // 4️⃣ Proxy the request to original Vercel static file / API
  const originalPath = req.url.replace(/^\/api\/auth-proxy/, '') || '/index.html';
  const origin = `https://${process.env.VERCEL_URL}`; // auto‑injected by Vercel
  const targetUrl = `${origin}${originalPath}`;

  try {
    const originRes = await fetch(targetUrl, {
      method: req.method,
      headers: Object.fromEntries(
        [...req.headers.entries()].filter(([k]) => k.toLowerCase() !== 'authorization')
      ),
    });
    // Pass through status, headers, body
    res.status(originRes.status);
    originRes.headers.forEach((value, key) => {
      if (key.toLowerCase() !== 'content-encoding') {
        res.setHeader(key, value);
      }
    });
    const body = await originRes.arrayBuffer();
    return res.send(Buffer.from(body));
  } catch (e) {
    console.error('Auth‑proxy error:', e);
    return res.status(500).send('Proxy error');
  }
};
