import test from 'node:test';
import assert from 'node:assert/strict';
import { createService } from './server.mjs';
test('service responds over HTTP', async () => { const server = createService(); await new Promise(resolve => server.listen(0, '127.0.0.1', resolve)); try { const response = await fetch(`http://127.0.0.1:${server.address().port}`); assert.equal(response.status, 200); assert.equal(await response.text(), 'Managed service ready\n'); } finally { await new Promise(resolve => server.close(resolve)); } });
