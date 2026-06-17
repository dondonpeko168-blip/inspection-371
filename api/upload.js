import { writeFileSync, unlinkSync, readFileSync, createWriteStream } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';
import { mkdtempSync, rmSync } from 'fs';
import { tmpdir } from 'os';
import { createHash } from 'crypto';
import { spawn } from 'child_process';

const __dirname = dirname(fileURLToPath(import.meta.url));
const DATA_GZ_PATH = join(__dirname, 'data.xlsx.gz');
const DATA_XLSX_PATH = join(__dirname, 'data.xlsx');
const DB_PATH = '/tmp/insp_371.db';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
};

function makeResponse(body, status = 200, contentType = 'application/json') {
  return new Response(body, { status, headers: { ...CORS_HEADERS, 'Content-Type': contentType } });
}

function json(data, status = 200) {
  return makeResponse(JSON.stringify(data), status);
}

// Simple multipart parser (no deps)
async function parseMultipart(buffer, boundary) {
  const parts = [];
  const b1 = Buffer.from('--' + boundary);
  const bEnd = Buffer.from('--' + boundary + '--');

  let pos = 0;
  while (pos < buffer.length) {
    // Find boundary
    let bi = buffer.indexOf(b1, pos);
    if (bi === -1) break;
    pos = bi + b1.length;
    if (buffer[pos] === 13) pos += 2; // skip \r\n
    if (buffer[pos] === 45) break; // '--' end

    // Find blank line (\r\n\r\n)
    let nl = buffer.indexOf(13, pos);
    let nl2 = buffer.indexOf(10, pos);
    let headerEnd = -1;
    if (nl !== -1 && nl2 !== -1) {
      headerEnd = Math.min(nl, nl2);
      // Check if this is \r\n\r\n
      if (nl2 === nl + 1 && buffer[nl + 2] === 10) headerEnd = nl + 2;
      else if (nl === buffer.indexOf(10, nl + 1) + 1) headerEnd = nl + 2;
    }
    if (headerEnd === -1 || headerEnd - pos > 4096) break;

    const headerStr = buffer.slice(pos, headerEnd).toString('utf-8');
    pos = headerEnd + (buffer[headerEnd] === 10 ? 1 : 2); // skip \n or \r\n

    // Find next boundary
    let nextBi = buffer.indexOf(b1, pos);
    if (nextBi === -1) break;

    // Check for -- end
    if (buffer.slice(nextBi, nextBi + bEnd.length).equals(bEnd)) break;

    // Data ends 2 bytes before boundary (\r\n)
    let dataEnd = nextBi - 2;
    while (dataEnd > pos && buffer[dataEnd] === 32) dataEnd--; // trim trailing space

    const data = buffer.slice(pos, dataEnd);
    const filenameMatch = headerStr.match(/filename="([^"]+)"/);

    if (filenameMatch) {
      parts.push({ filename: filenameMatch[1], data });
    }

    pos = nextBi + b1.length;
    if (buffer[pos] === 13) pos += 2;
  }
  return parts;
}

// Call Python to parse xlsx and return metadata
async function parseXlsxMeta(xlsxPath) {
  return new Promise((resolve, reject) => {
    const script = `
import sys, json, gzip
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
`;
    const child = spawn('python3.12', ['-c', script, xlsxPath]);
    let out = '', err = '';
    child.stdout.on('data', d => out += d);
    child.stderr.on('data', d => err += d);
    const timer = setTimeout(() => { child.kill(); reject(new Error('xlsx parse timeout')); }, 45);
    child.on('close', code => {
      clearTimeout(timer);
      if (code === 0) {
        try { resolve(JSON.parse(out)); } catch { reject(new Error('bad xlsx parse output')); }
      } else {
        reject(new Error(err || 'xlsx parse failed'));
      }
    });
  });
}

// Compress xlsx to gz using Python
async function compressGzip(inputPath, outputPath) {
  return new Promise((resolve, reject) => {
    const child = spawn('python3.12', ['-c', `
import gzip, sys
with open(sys.argv[1],'rb') as f:
    data = f.read()
with gzip.open(sys.argv[2],'wb', compresslevel=6) as gz:
    gz.write(data)
print('ok')
`], { cwd: __dirname });
    let err = '';
    child.stderr.on('data', d => err += d);
    const timer = setTimeout(() => { child.kill(); reject(new Error('gzip timeout')); }, 20);
    child.on('close', code => {
      clearTimeout(timer);
      if (code === 0) resolve(); else reject(new Error(err || 'gzip failed'));
    });
  });
}

export default async function handler(req) {
  if (req.method === 'OPTIONS') {
    return new Response(null, { status: 200, headers: CORS_HEADERS });
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

  let body;
  try {
    body = await req.arrayBuffer();
  } catch {
    return json({ error: 'Failed to read body' }, 400);
  }

  const parts = await parseMultipart(Buffer.from(body), boundary);
  const filePart = parts.find(p => p.filename);

  if (!filePart) return json({ error: 'No file uploaded' }, 400);
  if (!filePart.filename.endsWith('.xlsx')) return json({ error: 'Only .xlsx supported' }, 400);

  const tmpDir = mkdtempSync(tmpdir() + '/up_');
  const tmpXlsx = join(tmpDir, filePart.filename);
  const tmpGz = join(tmpDir, 'data.xlsx.gz');

  try {
    writeFileSync(tmpXlsx, filePart.data);

    // Parse and validate
    const parsed = await parseXlsxMeta(tmpXlsx);
    if (parsed.error) return json({ error: 'Failed to parse Excel: ' + parsed.error }, 400);

    // Compress and save
    await compressGzip(tmpXlsx, tmpGz);

    // Copy to api/ directory
    const gzData = readFileSync(tmpGz);
    writeFileSync(DATA_GZ_PATH, gzData);
    writeFileSync(DATA_XLSX_PATH, filePart.data);

    // Remove old DB to force rebuild
    try { unlinkSync(DB_PATH); } catch {}

    return json({
      success: true,
      filename: filePart.filename,
      rows: parsed.count,
      columns: parsed.headers,
      sample: parsed.rows.slice(0, 3).map((r, i) => {
        const obj = {};
        parsed.headers.forEach((h, j) => { obj[h] = r[j] || ''; });
        return obj;
      }),
    });

  } catch(e) {
    console.error('Upload error:', e);
    return json({ error: e.message }, 500);
  } finally {
    try { rmSync(tmpDir, { recursive: true, force: true }); } catch {}
  }
}