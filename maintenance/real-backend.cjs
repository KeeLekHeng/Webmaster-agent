// Required real password + MFA browser probe. No route interception or auth bypass.
'use strict';
const {spawn}=require('node:child_process');
const crypto=require('node:crypto');
let phase='start',browser,child;
const sleep=(ms)=>new Promise(resolve=>setTimeout(resolve,ms));
function totp(secret, now=Date.now()){
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  let bits='';
  for(const c of secret.toUpperCase().replace(/=+$/,'')){
    const index=alphabet.indexOf(c);if(index<0)throw Error('Invalid test factor');
    bits+=index.toString(2).padStart(5,'0');
  }
  const bytes=[];for(let i=0;i+8<=bits.length;i+=8)bytes.push(parseInt(bits.slice(i,i+8),2));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(now/30000)));
  const digest=crypto.createHmac('sha1',Buffer.from(bytes)).update(counter).digest();
  const offset=digest[digest.length-1]&15;
  return ((digest.readUInt32BE(offset)&0x7fffffff)%1000000).toString().padStart(6,'0');
}
async function main(){
  const {chromium}=require('/work/node_modules/@playwright/test');
  if(process.env.E2E_TEST_DATA!=='0'||process.env.REQUIRE_ADMIN_MFA!=='true')throw Error('Real mode required');
  if(!process.env.GUARDIAN_TEST_ADMIN_EMAIL||!process.env.GUARDIAN_TEST_ADMIN_PASSWORD)throw Error('Test account missing');
  child=spawn(process.execPath,['/work/node_modules/next/dist/bin/next','start','-p','3100'],
    {cwd:'/work',env:process.env,stdio:'ignore',shell:false});
  let ready=false;
  for(let i=0;i<60;i++){
    try{const r=await fetch('http://localhost:3100/api/health',{signal:AbortSignal.timeout(1000)});if(r.ok){ready=true;break;}}catch{}
    if(child.exitCode!==null)throw Error('Server exited');
    await sleep(500);
  }
  if(!ready)throw Error('Server not ready');
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext(); // No traces/video/saved auth storage.
  const page=await context.newPage();page.setDefaultTimeout(15000);
  phase='anonymous-redirect';
  await page.goto('http://localhost:3100/manage');
  await page.waitForURL(url=>url.pathname==='/manage/login');
  phase='password-login';
  await page.getByLabel('Email',{exact:true}).fill(process.env.GUARDIAN_TEST_ADMIN_EMAIL);
  await page.getByLabel('Password',{exact:true}).fill(process.env.GUARDIAN_TEST_ADMIN_PASSWORD);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  phase='mfa-enrollment';
  const secret=await page.locator('.admin-login__secret').innerText();
  if(30-(Math.floor(Date.now()/1000)%30)<5)await sleep(5500);
  await page.getByLabel('Authenticator code',{exact:true}).fill(totp(secret));
  await page.getByRole('button',{name:'Verify code',exact:true}).click();
  phase='mfa-management-access';
  await page.waitForURL(url=>url.pathname==='/manage');
  const response=await context.request.get('http://localhost:3100/api/manage/session');
  if(response.status()!==200)throw Error('Verified session missing');
  await page.goto('http://localhost:3100/manage/blogs');
  await page.getByRole('heading',{name:'Blog library',exact:true}).waitFor();
  phase='logout';
  await context.clearCookies();
  await page.goto('http://localhost:3100/manage');
  await page.waitForURL(url=>url.pathname==='/manage/login');
  process.stdout.write(JSON.stringify({real_password_mfa_browser:'passed'})+'\n');
}
module.exports={totp};
if(require.main===module)main().catch(()=>{process.stderr.write('GUARDIAN_REAL_AUTH_PROBE_FAILED:'+phase+'\n');process.exitCode=1;})
  .finally(async()=>{
    if(browser)await browser.close();
    if(child){child.kill('SIGTERM');await Promise.race([new Promise(resolve=>child.once('exit',resolve)),sleep(3000)]);if(child.exitCode===null)child.kill('SIGKILL');}
  });
