const { Buffer } = require('node:buffer');

// Environment variables – set in Vercel Dashboard (already added)
const USER = process.env.BASIC_AUTH_USER;
const PASS = process.env.BASIC_AUTH_PASS;

module.exports = async (req, res) => {
  // 1️⃣ 讀取 Authorization 標頭 (Node.js request, headers are plain objects)
  const authHeader = req.headers['authorization'];
  if (!authHeader) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Authentication required');
  }

  // 2️⃣ 解析 "Basic <base64>"
  const parts = authHeader.split(' ');
  if (parts.length !== 2) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid authentication header');
  }
  const encoded = parts[1];
  const decoded = Buffer.from(encoded, 'base64').toString();
  const [user, pass] = decoded.split(':');

  // 3️⃣ 驗證帳號密碼
  if (user !== USER || pass !== PASS) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid credentials');
  }

  // 4️⃣ Proxy 原始請求至 Vercel 靜態/API 端點
  const originalPath = req.url.replace(/^\/api\/auth-proxy/, '') || '/index.html';
  const origin = `https://${process.env.VERCEL_URL}`; // Vercel auto‑injectes this env var
  const targetUrl = `${origin}${originalPath}`;

  try {
    const originRes = await fetch(targetUrl, {
      method: req.method,
      headers: Object.fromEntries(
        Object.entries(req.headers).filter(([k]) => k.toLowerCase() !== 'authorization')
      ),
    });
    // Forward status, headers, body
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
