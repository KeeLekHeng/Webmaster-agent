// Fixed harmless probes, before candidate migration execution. No source values.
'use strict';
const net=require('node:net');
const dns=require('node:dns');
async function main(){
  const tcp=await new Promise(resolve=>{
    const socket=net.createConnection({host:'198.51.100.1',port:9});
    socket.setTimeout(1000);
    socket.once('connect',()=>{socket.destroy();resolve(false);});
    socket.once('error',()=>resolve(true));socket.once('timeout',()=>{socket.destroy();resolve(true);});
  });
  const resolver=new dns.Resolver();
  const externalDns=await new Promise(resolve=>{
    const timer=setTimeout(()=>{resolver.cancel();resolve(true);},1500);
    resolver.resolve4('example.com',(error,addresses)=>{clearTimeout(timer);resolve(Boolean(error)||!addresses?.length);});
  });
  if(!tcp||!externalDns)throw Error('Private network probe failed');
  process.stdout.write(JSON.stringify({tcp_blocked:true,dns_blocked:true}));
}
main().catch(()=>{process.stderr.write('GUARDIAN_NETWORK_PROBE_FAILED\n');process.exitCode=1;});
