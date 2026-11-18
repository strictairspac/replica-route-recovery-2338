import {workloadsApi} from '../api/workloads.js';
export const workloadsStore={items:[],async refresh(){this.items=await workloadsApi.list();return this.items;}};
