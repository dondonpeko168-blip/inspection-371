import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const INDEX_HTML = readFileSync(join(__dirname, '..', 'index.html'), 'utf-8');

export default async function handler(req, res) {
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  return res.status(200).send(INDEX_HTML);
}