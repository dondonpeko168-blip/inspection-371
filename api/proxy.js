import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const INDEX_HTML = readFileSync(join(__dirname, '..', 'index.html'), 'utf-8');

const VERCEL_URL = process.env.VERCEL_URL || 'inspection-371.vercel.app';
const PYTHON_DEST = `https://${VERCEL_URL}/api/index.py`;

export default async function handler(req, res) {
  try {
    const rawUrl = req.url || '/';
    const queryIdx = rawUrl.indexOf('?');
    const path = queryIdx >= 0 ? rawUrl.substring(0, queryIdx) : rawUrl;
    const qs = queryIdx >= 0 ? rawUrl.substring(queryIdx) : '';

    // Serve index.html for root
    if (path === '/' || path === '/index.html') {
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      return res.status(200).send(INDEX_HTML);
    }

    // Proxy API calls to Python backend.
    // Build the target path differently:
    // - Vercel rewrite sends /api/init -> this becomes /api/init in req.url
    // - We need to forward to the Python handler directly to avoid loops
    const targetUrl = `${PYTHON_DEST}${path}${qs}`;

    // req.headers is a plain object in Vercel runtime, not a Map
    const upstreamHeaders = { ...req.headers };
    delete upstreamHeaders['host'];

    const upstream = await fetch(targetUrl, {
      method: req.method,
      headers: upstreamHeaders,
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
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    return res.status(500).send(`Proxy error: ${err.message}`);
  }
}