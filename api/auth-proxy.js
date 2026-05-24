import { Buffer } from 'node:buffer';

const USER = process.env.BASIC_AUTH_USER;
const PASS = process.env.BASIC_AUTH_PASS;

export default async function handler(req, res) {
  // 1️⃣ 讀取 Authorization 標頭
  const authHeader = req.headers.get('authorization');
  if (!authHeader) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Authentication required');
  }

  // 2️⃣ 解析 "Basic <base64>"
  const [, encoded] = authHeader.split(' ') ?? [];
  if (!encoded) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid authentication header');
  }
  const decoded = Buffer.from(encoded, 'base64').toString();
  const [user, pass] = decoded.split(':');

  // 3️⃣ 驗證帳號密碼
  if (user !== USER || pass !== PASS) {
    res.setHeader('WWW-Authenticate', 'Basic realm="Protected Area"');
    return res.status(401).send('Invalid credentials');
  }

  // 4️⃣ 取得原始請求路徑
  const originalPath = req.url.replace(/^\/api\/auth-proxy/, '') || '/index.html';
  const origin = `https://${process.env.VERCEL_URL}`;
  const targetUrl = `${origin}${originalPath.startsWith('/') ? '' : '/'}${originalPath}`;

  try {
    const originRes = await fetch(targetUrl, {
      method: req.method,
      headers: Object.fromEntries(
        [...req.headers.entries()].filter(
          ([k]) => k.toLowerCase() !== 'authorization'
        )
      ),
    });

    // 把後端回傳的 header、status、body 轉回給使用者
    res.status(originRes.status);
    originRes.headers.forEach((value, key) => {
      if (key.toLowerCase() !== 'content-encoding') {
        res.setHeader(key, value);
      }
    });
    const body = await originRes.arrayBuffer();
    return res.send(Buffer.from(body));
  } catch (e) {
    console.error('Auth-proxy error:', e);
    return res.status(500).send('Proxy error');
  }
}