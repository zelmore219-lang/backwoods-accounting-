const {Readable}=require('node:stream');
function headersOf(values){const headers=new Headers();for(const [name,value] of Object.entries(values||{})){for(const item of Array.isArray(value)?value:[value])if(typeof item==='string')headers.append(name,item);}return headers;}
// Electron net.fetch rejects manual redirects before exposing a Response.
// Use its documented request redirect event to return the redirect to core,
// which validates the destination before issuing the next request.
module.exports=function createTransport(net,session){return (url,options={})=>new Promise((resolve,reject)=>{
 let settled=false,request;
 const fail=error=>{if(!settled){settled=true;reject(error);}};
 const abort=()=>{fail(options.signal?.reason||Error('Update request aborted.'));request?.abort();};
 if(options.signal?.aborted){abort();return;}
 try{
  request=net.request({url,method:'GET',redirect:'manual',credentials:'omit',...(session?{session}:{})});
  options.signal?.addEventListener('abort',abort,{once:true});
  request.on('error',error=>fail(error));
  request.on('redirect',(status,_method,target,values)=>{
   if(settled)return;
   try{const headers=headersOf(values);headers.set('location',target);settled=true;resolve(new Response(null,{status,headers}));}
   catch(error){settled=false;fail(error);}
   finally{options.signal?.removeEventListener('abort',abort);request.abort();}
  });
  request.on('response',incoming=>{
   if(settled){incoming.destroy();return;}
   try{const response=new Response(Readable.toWeb(incoming),{status:incoming.statusCode,headers:headersOf(incoming.headers)});settled=true;resolve(response);incoming.on('end',()=>options.signal?.removeEventListener('abort',abort));incoming.on('close',()=>options.signal?.removeEventListener('abort',abort));}
   catch(error){fail(error);request.abort();}
  });
  request.end();
 }catch(error){options.signal?.removeEventListener('abort',abort);fail(error);}
});};
