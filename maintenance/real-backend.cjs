// Required real password + MFA browser probe. No route interception or auth bypass.
'use strict';
const {spawn}=require('node:child_process');
const crypto=require('node:crypto');
let phase='start',browser,child;
const origin='http://localhost:3100';
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
async function startServer(mfaRequired){
  child=spawn(process.execPath,['/work/node_modules/next/dist/bin/next','start','-p','3100'],
    {cwd:'/work',env:{...process.env,REQUIRE_ADMIN_MFA:mfaRequired},stdio:'ignore',shell:false});
  let ready=false;
  for(let i=0;i<60;i++){
    try{const r=await fetch('http://localhost:3100/api/health',{signal:AbortSignal.timeout(1000)});if(r.ok){ready=true;break;}}catch{}
    if(child.exitCode!==null)throw Error('Server exited');
    await sleep(500);
  }
  if(!ready)throw Error('Server not ready');
}
async function stopServer(){
  if(!child)return;
  const stopped=new Promise(resolve=>child.once('exit',resolve));
  child.kill('SIGTERM');await Promise.race([stopped,sleep(3000)]);
  if(child.exitCode===null){child.kill('SIGKILL');await stopped;}
  child=undefined;
}
async function passwordLogin(page){
  await page.getByLabel('Email',{exact:true}).fill(process.env.GUARDIAN_TEST_ADMIN_EMAIL);
  await page.getByLabel('Password',{exact:true}).fill(process.env.GUARDIAN_TEST_ADMIN_PASSWORD);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
}
async function verifyMfa(){
  await startServer('true');
  const context=await browser.newContext(); // No traces/video/saved auth storage.
  const page=await context.newPage();page.setDefaultTimeout(15000);
  phase='anonymous-redirect';
  await page.goto('http://localhost:3100/manage');
  await page.waitForURL(url=>url.pathname==='/manage/login');
  phase='password-login';
  await passwordLogin(page);
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
  await context.close();
  await stopServer();
}
async function draftRows(slug,anonymous=false){
  const key=anonymous?process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:process.env.SUPABASE_SECRET_KEY;
  const response=await fetch('http://127.0.0.1:8000/rest/v1/blogs?select=slug,title,status,blocks&slug=eq.'+encodeURIComponent(slug),
    {headers:{apikey:key,Authorization:'Bearer '+key},signal:AbortSignal.timeout(10000)});
  if(response.status!==200)throw Error('Draft persistence read failed');
  const rows=await response.json();
  if(!Array.isArray(rows)||rows.length>1)throw Error('Unexpected draft inventory');
  return rows;
}
async function verifyUat(){
  phase='uat-start';await startServer('false');
  const context=await browser.newContext();
  const page=await context.newPage();page.setDefaultTimeout(15000);
  const slug='guardian-ci-draft-'+crypto.randomBytes(8).toString('hex');
  const draft={slug,title:'Guardian synthetic draft',summary:'Disposable CI content',status:'draft',
    blocks:[{type:'paragraph',text:'Synthetic draft body'}]};
  const headers={Origin:origin};
  phase='uat-anonymous-rejection';
  await page.goto(origin+'/manage');
  await page.waitForURL(url=>url.pathname==='/manage/login');
  if((await context.request.post(origin+'/api/manage/blogs',{headers,data:draft})).status()!==401)
    throw Error('Anonymous mutation was not rejected');
  if((await draftRows(slug)).length!==0)throw Error('Anonymous mutation persisted');
  phase='uat-password-login';await passwordLogin(page);
  await page.waitForURL(url=>url.pathname==='/manage');
  if((await context.request.get(origin+'/api/manage/session')).status()!==200)throw Error('UAT session missing');
  phase='uat-draft-create';
  const created=await context.request.post(origin+'/api/manage/blogs',{headers,data:draft});
  if(created.status()!==200)throw Error('Draft create failed');
  const createdBody=await created.json();
  if(createdBody.slug!==slug||createdBody.status!=='draft')throw Error('Draft create result invalid');
  let rows=await draftRows(slug);
  if(rows.length!==1||rows[0].title!==draft.title||rows[0].status!=='draft'||rows[0].blocks?.[0]?.text!==draft.blocks[0].text)
    throw Error('Created draft not persisted');
  if((await draftRows(slug,true)).length!==0)throw Error('Private draft publicly readable');
  phase='uat-draft-read';
  await page.goto(origin+'/manage/blogs/'+slug);
  await page.getByPlaceholder('Title',{exact:true}).waitFor();
  const {expect}=require('/work/node_modules/@playwright/test');
  await expect(page.getByPlaceholder('Title',{exact:true})).toHaveValue(draft.title);
  await expect(page.locator('.blog-editor__paragraph textarea').first()).toHaveValue(draft.blocks[0].text);
  phase='uat-draft-update';
  const updated={...draft,title:'Guardian synthetic draft edited',blocks:[{type:'paragraph',text:'Verified updated body'}]};
  if((await context.request.put(origin+'/api/manage/blogs',{headers,data:updated})).status()!==200)throw Error('Draft update failed');
  rows=await draftRows(slug);
  if(rows.length!==1||rows[0].title!==updated.title||rows[0].blocks?.[0]?.text!==updated.blocks[0].text)
    throw Error('Updated draft not persisted');
  await page.reload();
  await expect(page.getByPlaceholder('Title',{exact:true})).toHaveValue(updated.title);
  await expect(page.locator('.blog-editor__paragraph textarea').first()).toHaveValue(updated.blocks[0].text);
  phase='uat-draft-delete';
  // Leave the editor before deletion, so autosave cannot race the cleanup.
  await page.goto(origin+'/manage/blogs');
  if((await context.request.delete(origin+'/api/manage/blogs?slug='+slug,{headers})).status()!==200)
    throw Error('Draft delete failed');
  if((await draftRows(slug)).length!==0)throw Error('Deleted draft still persisted');
  phase='uat-logout';
  if((await context.request.post(origin+'/api/manage/signout',{headers,maxRedirects:0})).status()!==303)
    throw Error('Signout failed');
  if((await context.request.get(origin+'/api/manage/session')).status()!==401)throw Error('Signed-out API accessible');
  await page.goto(origin+'/manage');
  await page.waitForURL(url=>url.pathname==='/manage/login');
  await context.close();await stopServer();
}
async function main(){
  const {chromium}=require('/work/node_modules/@playwright/test');
  if(process.env.E2E_TEST_DATA!=='0'||process.env.REQUIRE_ADMIN_MFA!=='true'||
     process.env.NEXT_PUBLIC_SUPABASE_URL!=='http://127.0.0.1:8000'||process.env.APP_URL!==origin)
    throw Error('Isolated real mode required');
  if(!process.env.GUARDIAN_TEST_ADMIN_EMAIL||!process.env.GUARDIAN_TEST_ADMIN_PASSWORD||!process.env.SUPABASE_SECRET_KEY)
    throw Error('Test account missing');
  browser=await chromium.launch({headless:true});
  await verifyMfa();await verifyUat();
  process.stdout.write(JSON.stringify({real_password_mfa_browser:'passed',uat_admin_browser:'passed'})+'\n');
}
module.exports={totp};
if(require.main===module)main().catch(()=>{process.stderr.write('GUARDIAN_REAL_AUTH_PROBE_FAILED:'+phase+'\n');process.exitCode=1;})
  .finally(async()=>{
    if(browser)await browser.close();
    await stopServer();
  });
