import {backupsApi,recoveriesApi} from '../api/backups.js';
export const backupsStore={
  backups:[],recoveries:[],
  async refresh(){
    const [backups,recoveries]=await Promise.all([backupsApi.list(),recoveriesApi.list()]);
    this.backups=backups;this.recoveries=recoveries;return this;
  },
};
