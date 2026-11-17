import {nodesApi} from '../api/nodes.js';
export const nodesStore={items:[],async refresh(){this.items=await nodesApi.list();return this.items;}};
