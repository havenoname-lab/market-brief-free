import test from 'node:test';
import assert from 'node:assert/strict';
import worker from '../worker/index.mjs';

const request=(path,headers={},method='GET',body)=>new Request('https://news.example'+path,{headers,method,body});
const auth={authorization:'Basic '+btoa('reader:test-reader-password-123')};
const env={READER_PASSWORD:'test-reader-password-123',SYNC_TOKEN:'test-sync-token-long-enough-123456',UI_VERSION:'test',ASSETS:{fetch:async()=>new Response('asset')}};

test('cloud refuses public data without a configured reader password',async()=>{
 const r=await worker.fetch(request('/api/articles'),{...env,READER_PASSWORD:''});
 assert.equal(r.status,503);
});
test('health is public but dashboard requires login',async()=>{
 assert.equal((await worker.fetch(request('/healthz'),env)).status,200);
 assert.equal((await worker.fetch(request('/'),env)).status,401);
 assert.equal((await worker.fetch(request('/',auth),env)).status,200);
});
test('reader cannot use sync endpoints',async()=>{
 assert.equal((await worker.fetch(request('/api/admin/import',auth,'POST','{}'),env)).status,401);
});
test('pagination and hours are bounded before database access',async()=>{
 assert.equal((await worker.fetch(request('/api/articles?limit=10000',auth),env)).status,400);
 assert.equal((await worker.fetch(request('/api/articles?hours=0',auth),env)).status,400);
});
test('manual refresh does not pretend it fetched source data',async()=>{
 const r=await worker.fetch(request('/api/refresh',auth,'POST'),env);
 assert.equal((await r.json()).status,'scheduled');
});
test('collector state uses keyset pagination',async()=>{
 const sql=[];
 const DB={prepare(query){sql.push(query);return {bind(){return this;},all:async()=>({results:[]}),first:async()=>null};}};
 const r=await worker.fetch(request('/api/admin/state?after=abc',{authorization:'Bearer '+env.SYNC_TOKEN}),{...env,DB});
 assert.equal(r.status,200);assert.ok(sql[0].includes('WHERE id>?'));assert.ok(!sql[0].includes('OFFSET'));
});
