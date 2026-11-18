import {api} from './client.js';
export const backupsApi={
  list:()=>api('/backups'),
  detail:id=>api('/backups/'+id),
  create:data=>api('/backups','POST',data),
  retry:id=>api('/backups/'+id+'/retry','POST'),
  recoveries:id=>api('/backups/'+id+'/recoveries'),
};
export const recoveriesApi={
  list:()=>api('/recoveries'),
  detail:id=>api('/recoveries/'+id),
  create:data=>api('/recoveries','POST',data),
  retry:id=>api('/recoveries/'+id+'/retry','POST'),
};
