import { createServer } from 'node:http';
import { pathToFileURL } from 'node:url';
export function createService() { return createServer((_request, response) => { response.writeHead(200, {'content-type':'text/plain'}); response.end('Managed service ready\n'); }); }
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const server = createService();
  server.listen(Number(process.env.PORT ?? 8080), '127.0.0.1');
  for (const signal of ['SIGINT','SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
}
