// Edge Function: 專門處理 /api/upload 和 /api/upload-* 路徑的 CORS preflight
// POST 等由 Python serverless 處理
// 注意：/api/upload（無額外path）也要匹配 → 用 /api/upload*

export const config = {
  matcher: ['/api/upload', '/api/upload-file', '/api/upload-url', '/api/upload-complete', '/api/upload*'],
};

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
  // For non-OPTIONS requests, forward to origin
  // Vercel routes this to the Python serverless function (index.py)
  return fetch(req);
}