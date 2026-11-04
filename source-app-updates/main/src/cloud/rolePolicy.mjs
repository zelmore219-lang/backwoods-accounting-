export const ROLES = Object.freeze({
  catalog: ['owner','admin','administrator','manager','sales','warehouse','packer','inventory','driver','accountant','accounting'],
  submitOrder: ['owner','admin','administrator','manager','sales'],
  pack: ['owner','admin','administrator','manager','warehouse','packer','inventory'],
  deliver: ['owner','admin','administrator','manager','driver']
});
export function authorize(profile,action,uid){
  if(!profile || profile.active!==true || profile.authUid!==uid || !ROLES[action]?.includes(profile.role))
    throw new Error('Wholesale permission denied for '+action);
  return true;
}
