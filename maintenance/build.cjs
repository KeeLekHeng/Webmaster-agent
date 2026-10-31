// Serve cached font bytes over container loopback; external egress stays blocked.
'use strict';
const http = require('node:http');
const fs = require('node:fs');
const {spawn} = require('node:child_process');
const server = http.createServer((request, response) => {
  if (!['GET','HEAD'].includes(request.method) || !/^\/[a-f0-9]{64}\.(?:woff2?|ttf|otf)$/.test(request.url)) {
    response.writeHead(404); response.end(); return;
  }
  try {
    const data = fs.readFileSync('/fixtures'+request.url);
    response.writeHead(200, {'Content-Type':'application/octet-stream','Content-Length':data.length});
    response.end(request.method==='HEAD' ? undefined : data);
  } catch { response.writeHead(404); response.end(); }
});
let child;
server.on('error', () => { if (child) child.kill('SIGTERM'); process.exitCode=1; });
server.listen(37913,'127.0.0.1', () => {
  child=spawn('pnpm',['run','build'],{cwd:'/work',env:process.env,stdio:'inherit',shell:false});
  child.on('error',()=>server.close(()=>{process.exitCode=1;}));
  child.on('exit',(code)=>server.close(()=>{process.exitCode=code ?? 1;}));
});
for (const signal of ['SIGTERM','SIGINT']) process.on(signal,()=>{
  if (child) child.kill(signal);
  server.close(()=>{process.exitCode=1;});
});
