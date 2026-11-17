import {request_setsApi} from '../api/request_sets.js';
export const request_setsStore={items:[],async refresh(){this.items=await request_setsApi.list();return this.items;}};
