const {URL}=require('node:url');

function companyServer(value){
  if(!value)return null;
  let url;
  try{url=new URL(value.trim());}catch{throw new Error('The shared accounting address must be an HTTPS origin.');}
  if(url.protocol!=='https:'||url.username||url.password||url.pathname!=='/'||url.search||url.hash)
    throw new Error('The shared accounting address must be an HTTPS origin without credentials, a path, query or fragment.');
  return url.origin;
}
module.exports={companyServer};
