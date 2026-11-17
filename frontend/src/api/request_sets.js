import {api} from './client.js';
export const request_setsApi={list:()=>api('/request_sets'),create:data=>api('/request_sets','POST',data)};
