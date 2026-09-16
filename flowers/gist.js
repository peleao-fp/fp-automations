// Minimal GitHub Gist client (Node 20 global fetch)
const API = 'https://api.github.com/gists/';

function headers() {
  return {
    'Authorization': `Bearer ${process.env.GH_TOKEN}`,
    'Accept':        'application/vnd.github.v3+json',
    'User-Agent':    'fp-automations',
  };
}

async function getGist(gistId) {
  const res = await fetch(API + gistId, { headers: headers() });
  if (!res.ok) throw new Error(`Gist GET ${gistId}: ${res.status} ${(await res.text()).slice(0, 200)}`);
  return res.json();
}

// Content of the first file (email body gist) or of a named file
async function readGistFile(gistId, fileName) {
  const gist = await getGist(gistId);
  const file = fileName ? gist.files?.[fileName] : Object.values(gist.files || {})[0];
  if (!file) return null;
  // Large files come back truncated → fetch raw
  if (file.truncated && file.raw_url) {
    const raw = await fetch(file.raw_url, { headers: headers() });
    return raw.text();
  }
  return file.content;
}

// files: { 'name.json': 'content string' }
async function writeGistFiles(gistId, files) {
  const body = { files: Object.fromEntries(Object.entries(files).map(([k, v]) => [k, { content: v }])) };
  const res = await fetch(API + gistId, {
    method:  'PATCH',
    headers: { ...headers(), 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Gist PATCH ${gistId}: ${res.status} ${(await res.text()).slice(0, 200)}`);
}

async function deleteGist(gistId) {
  const res = await fetch(API + gistId, { method: 'DELETE', headers: headers() });
  if (!res.ok && res.status !== 404) throw new Error(`Gist DELETE ${gistId}: ${res.status}`);
}

module.exports = { readGistFile, writeGistFiles, deleteGist };
