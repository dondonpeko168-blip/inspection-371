// Node.js serverless upload handler (no edge — multipart needs buffer)
// CORS is handled by the /api/upload route rewrite in vercel.json
import { writeFileSync, unlinkSync, readFileSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { mkdtempSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { spawn } from 'child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_GZ_PATH = join(__dirname, 'data.xlsx.gz');
const DATA_XLSX_PATH = join(__dirname, 'data.xlsx');
const DB_PATH = '/tmp/insp_371.db';

function parseMultipart(buffer, boundary) {
  const parts = [];
  const b1 = Buffer.from('--' + boundary);
  const bEnd = Buffer.from('--' + boundary + '--');
  const NL = Buffer.from('\r\n');

  let pos = 0;
  while (pos < buffer.length) {
    const bi = buffer.indexOf(b1, pos);
    if (bi === -1) break;
    pos = bi + b1.length;
    if (buffer[pos] === 45 && buffer[pos+1] === 45) break; // '--' end
    if (buffer[pos] === 13 || buffer[pos] === 10) {
      pos += buffer[pos] === 13 ? 2 : 1;
    }

    // Find blank line
    const nlIdx = buffer.indexOf(NL, pos);
    if (nlIdx === -1 || nlIdx - pos > 8192) break;
    const headerStr = buffer.slice(pos, nlIdx).toString('utf-8');
    pos = nlIdx + 2; // skip \r\n

    // Next boundary
    let nextBi = buffer.indexOf(b1, pos);
    if (nextBi === -1) break;

    // Check for -- end marker
    if (buffer.slice(nextBi, nextBi + bEnd.length).equals(bEnd)) break;

    const dataEnd = Math.max(pos, nextBi - 2);
    const data = buffer.slice(pos, dataEnd);
    const fnMatch = headerStr.match(/filename="([^"]+)"/);

    if (fnMatch) parts.push({ filename: fnMatch[1], data });
    pos = nextBi + b1.length;
    if (buffer[pos] === 13) pos += 2;
  }
  return parts;
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Content-Type',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    },
  });
}

async function runPython(script, args = []) {
  return new Promise((resolve, reject) => {
    const child = spawn('python3.12', ['-c', script, ...args], { cwd: __dirname });
    let out = '', err = '';
    child.stdout.on('data', d => out += d);
    child.stderr.on('data', d => err += d);
    const timer = setTimeout(() => { child.kill(); reject(new Error('timeout')); }, 50);
    child.on('close', code => {
      clearTimeout(timer);
      resolve({ code, out, err });
    });
  });
}

export default async function handler(req) {
  // OPTIONS handled here — explicitly to satisfy Vercel proxy
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
      },
    });
  }

  if (req.method !== 'POST') {
    return json({ error: 'Method not allowed' }, 405);
  }

  const ct = req.headers.get('content-type') || '';
  if (!ct.includes('multipart/form-data')) {
    return json({ error: 'Expected multipart/form-data' }, 400);
  }

  const boundary = ct.match(/boundary=(.+)/)?.[1];
  if (!boundary) return json({ error: 'Missing boundary' }, 400);

  let bodyBuffer;
  try {
    bodyBuffer = await req.arrayBuffer();
  } catch {
    return json({ error: 'Failed to read body' }, 400);
  }

  const parts = parseMultipart(Buffer.from(bodyBuffer), boundary);
  const filePart = parts.find(p => p.filename);

  if (!filePart) return json({ error: 'No file uploaded' }, 400);
  if (!filePart.filename.endsWith('.xlsx')) return json({ error: 'Only .xlsx supported' }, 400);

  const tmpDir = mkdtempSync(tmpdir() + '/up_');
  const tmpXlsx = join(tmpDir, filePart.filename);
  const tmpGz = join(tmpDir, 'data.xlsx.gz');

  try {
    writeFileSync(tmpXlsx, filePart.data);

    // Parse xlsx
    const { code, out, err } = await runPython(`
import sys, json
try:
    import openpyxl
    wb = openpyxl.load_workbook(sys.argv[1], read_only=True)
    ws = wb.active
    headers = [str(cell.value).strip() if cell.value is not None else f"col_{i}"
               for i, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1)))]
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        r = [str(v) if v is not None else "" for v in row]
        while len(r) < len(headers): r.append("")
        rows.append(r[:len(headers)])
    wb.close()
    print(json.dumps({"headers": headers, "rows": rows, "count": len(rows)}))
except Exception as e:
    print(json.dumps({"error": str(e)}))
`, [tmpXlsx]);

    let parsed;
    try { parsed = JSON.parse(out); } catch { return json({ error: 'parse failed: ' + err }, 400); }
    if (parsed.error) return json({ error: 'parse: ' + parsed.error }, 400);

    // Compress xlsx to gz
    const gzResult = await runPython(`
import gzip, sys
with open(sys.argv[1],'rb') as f:
    data = f.read()
with gzip.open(sys.argv[2],'wb', compresslevel=6) as gz:
    gz.write(data)
print('ok')
`, [tmpXlsx, tmpGz]);
    if (gzResult.code !== 0) return json({ error: 'gzip failed: ' + gzResult.err }, 500);

    // Copy to api dir
    try {
      writeFileSync(DATA_GZ_PATH, readFileSync(tmpGz));
      writeFileSync(DATA_XLSX_PATH, filePart.data);
      try { unlinkSync(DB_PATH); } catch {}
    } catch(e) { return json({ error: 'file write: ' + e.message }, 500); }

    return json({
      success: true,
      filename: filePart.filename,
      rows: parsed.count,
      columns: parsed.headers,
      sample: parsed.rows.slice(0, 3).map(r => {
        const obj = {};
        parsed.headers.forEach((h, j) => { obj[h] = r[j] || ''; });
        return obj;
      }),
    });

  } catch(e) {
    return json({ error: e.message }, 500);
  } finally {
    try { rmSync(tmpDir, { recursive: true, force: true }); } catch {}
  }
}