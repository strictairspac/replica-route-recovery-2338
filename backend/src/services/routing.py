"""Deterministic routing replay: integer log positions in a named lineage, never a live replica probe."""
import copy,hashlib,json

def simulate(node_inputs,events,max_delay_ms,sticky_ms):
    if not 1<=len(node_inputs)<=12:raise ValueError('需要1–12个节点')
    if not 1<=len(events)<=100:raise ValueError('需要1–100个时序事件')
    if max_delay_ms<0 or sticky_ms<0:raise ValueError('延迟门槛和粘滞时间不得为负')
    if len({x['name'] for x in node_inputs})!=len(node_inputs):raise ValueError('节点名必须唯一')
    primaries=[x for x in node_inputs if x['role']=='primary']
    if len(primaries)!=1:raise ValueError('必须且只能配置一个主节点')
    nodes={x['name']:copy.deepcopy(x) for x in node_inputs};primary=nodes[primaries[0]['name']];lineage=primary['lineage'];sessions={};trace=[];last_time=-1
    if any(n['role']=='replica' and n['lineage']==lineage and n['position']>primary['position'] for n in nodes.values()):raise ValueError('同日志谱系副本位点不得高于主库初始位点')
    for index,event in enumerate(events):
        at=event['at_ms'];kind=event['kind'];session=event.get('session','default')
        if at<last_time:raise ValueError('事件必须按时间非递减排列')
        last_time=at;row={'index':index+1,'at_ms':at,'kind':kind,'session':session,'node':None,'decision':'applied','reason':'','required_position':sessions.get(session,{}).get('required',0),'observed_position':None,'safe':True}
        if kind in ('node_down','node_up','replicate'):
            target=nodes.get(event.get('node'))
            if not target:raise ValueError('事件引用未知节点：'+str(event.get('node')))
            row['node']=target['name']
            if kind=='replicate':
                if target['role']!='replica':raise ValueError('replicate仅允许副本节点')
                if target['status']!='healthy':raise ValueError('停机副本不能应用日志，请先node_up')
                if target['lineage']!=lineage:raise ValueError('日志谱系不匹配，不得复制当前主库日志')
                pos=event.get('position');delay=event.get('delay_ms')
                if pos is None or delay is None or delay<0 or not target['position']<=pos<=primary['position']:raise ValueError('复制位点必须单调且不超过已提交主库位点')
                target['position']=pos;target['delay_ms']=delay;row['observed_position']=pos;row['reason']='副本应用已提交日志'
            else:
                target['status']='down' if kind=='node_down' else 'healthy';row['reason']='节点下线' if kind=='node_down' else '节点恢复'
        elif kind=='write':
            if primary['status']!='healthy':row.update(decision='rejected',reason='主库不可用，拒绝写入')
            else:
                primary['position']+=1;sessions[session]={'required':primary['position'],'lineage':lineage,'last_write_ms':at}
                row.update(node=primary['name'],decision='routed',reason='写入主库并记录会话位点',required_position=primary['position'],observed_position=primary['position'])
        elif kind=='read':
            state=sessions.get(session,{'required':0,'lineage':lineage,'last_write_ms':None});required=state['required'];row['required_position']=required
            sticky=state['last_write_ms'] is not None and at-state['last_write_ms']<sticky_ms
            eligible=[n for n in nodes.values() if n['role']=='replica' and n['status']=='healthy' and n['lineage']==state['lineage'] and n['position']>=required and n['delay_ms']<=max_delay_ms]
            candidates=sorted(eligible,key=lambda n:(n['delay_ms'],-n['position'],n['name']))
            selected=None
            if sticky:
                if primary['status']=='healthy' and primary['lineage']==state['lineage'] and primary['position']>=required:selected=primary;row['reason']='写后读粘滞：保持主库'
                else:row['reason']='粘滞期主库不可用，拒绝不确定读取'
            elif candidates:selected=candidates[0];row['reason']='副本位点满足会话且延迟达标'
            elif primary['status']=='healthy' and primary['lineage']==state['lineage'] and primary['position']>=required:selected=primary;row['reason']='无安全达标副本，回退主库'
            else:row['reason']='主库不可用且无安全达标副本，拒绝读取'
            if selected:row.update(node=selected['name'],decision='routed',observed_position=selected['position'],safe=selected['position']>=required and selected['lineage']==state['lineage'])
            else:row['decision']='rejected'
            row['replica_checks']=[{'name':n['name'],'healthy':n['status']=='healthy','same_lineage':n['lineage']==state['lineage'],'position_sufficient':n['position']>=required,'delay_within_limit':n['delay_ms']<=max_delay_ms} for n in nodes.values() if n['role']=='replica']
        else:raise ValueError('未知事件类型')
        trace.append(row)
    requests=[r for r in trace if r['kind'] in ('read','write')];routed=[r for r in requests if r['decision']=='routed'];rejected=[r for r in requests if r['decision']=='rejected'];safe=all(r['safe'] for r in routed)
    result={'mode':'受控复制路由模型 / 非真实复制集群','lineage':lineage,'trace':trace,'sessions':sessions,'final_nodes':list(nodes.values()),'summary':{'requests':len(requests),'routed':len(routed),'rejected':len(rejected),'replica_reads':sum(r['kind']=='read' and r['node']!=primary['name'] for r in routed),'primary_reads':sum(r['kind']=='read' and r['node']==primary['name'] for r in routed),'all_routed_reads_safe':safe},'policy':{'max_delay_ms':max_delay_ms,'sticky_ms':sticky_ms,'position_model':'同一命名日志谱系的单调整数位点，不是完整GTID集合','sticky_boundary':'at_ms - last_write_ms < sticky_ms','replica_tie_break':'delay升序 / position降序 / name字典序'}}
    result['checksum']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest();return result
