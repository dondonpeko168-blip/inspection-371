// Edge Function: 搶在Vercel proxy之前處理CORS preflight（只有OPTIONS）
// POST 等非OPTIONS 請求由 Python serverless 處理
// 注意：Edge Functions 的 matcher 可以精確控制哪些路徑/方法
// 這裡用 /api/upload 和 /api/upload-file 的 OPTIONS preflight 專門處理

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Max-Age': '86400',
      },
    });
  }
  // For GET/POST: let the request continue to the origin
  // Vercel will route it based on vercel.json → /api/index.py
  return fetch(req, { signal: AbortSignal.timeout(30000) });
}