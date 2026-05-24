// Basic Auth proxy for any Vercel project (works on Free plan)
// Environment variables BASIC_AUTH_USER and BASIC_AUTH_PASS must be set in Vercel dashboard.

module.exports = async (req, res) => {
  const USER = process.env.BASIC_AUTH_USER;
  const PASS = process.env.BASIC_AUTH_PASS;

  // 1️⃣ Get Authorization header
  const authHeader = req.headers.get('authorization');
  if (!authHeader) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Authentication required');
  }

  // 2️⃣ Parse "Basic <base64>"
  const parts = authHeader.split(' ');
  if (parts.length !== 2) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid authentication header');
  }
  const encoded = parts[1];
  const decoded = Buffer.from(encoded, 'base64').toString();
  const [user, pass] = decoded.split(':');

  // 3️⃣ Verify credentials
  if (user !== USER || pass !== PASS) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid credentials');
  }

  // 4️⃣ Build the target path (remove the /api/auth-proxy prefix)
  const targetPath = req.url.replace(/^\/api\/auth-proxy/, '') || '/index.html';
  // Vercel automatically injects VERCEL_URL env var with the current domain
  const origin = `https://${process.env.VERCEL_URL}`;
  const targetUrl = `${origin}${targetPath}`;

  try {
    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers: Object.fromEntries(
        [...req.headers.entries()].filter(([k]) => k.toLowerCase() !== 'authorization')
      ),
    });

    // Forward status and selected headers
    res.status(upstream.status);
    upstream.headers.forEach((value, key) => {
      if (key.toLowerCase() !== 'content-encoding') {
        res.setHeader(key, value);
      }
    });
    const body = await upstream.arrayBuffer();
    return res.send(Buffer.from(body));
  } catch (e) {
    console.error('Auth‑proxy error:', e);
    return res.status(500).send('Proxy error');
  }
};
