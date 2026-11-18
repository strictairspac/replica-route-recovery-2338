import {api} from './client.js';
export const workloadsApi={list:()=>api('/workloads'),create:data=>api('/workloads','POST',data)};
