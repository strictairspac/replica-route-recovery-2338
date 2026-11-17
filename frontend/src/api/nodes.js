import {api} from './client.js';
export const nodesApi={list:()=>api('/nodes'),create:data=>api('/nodes','POST',data)};
