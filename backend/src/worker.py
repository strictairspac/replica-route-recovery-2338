import traceback,json
from pathlib import Path
from src.config.database import Session
from src.models.entities import Trial
from src.services.trials import queue
from src.services.routing import simulate
while True:
    Path('/tmp/worker-heartbeat').touch()
    item=queue.blpop('replicaroute:queue',timeout=2)
    if not item:continue
    ident=int(item[1])
    try:
        with Session() as db:
            obj=db.get(Trial,ident);obj.status='running';db.commit();snapshot=obj.input_snapshot;delay=obj.max_delay_ms;sticky=obj.sticky_ms
        result=simulate(snapshot['nodes'],snapshot['request_set']['events'],delay,sticky)
        with Session() as db:
            obj=db.get(Trial,ident);obj.result=result;obj.status='completed';db.commit()
        Path(f'/artifacts/route-{ident}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as e:
        traceback.print_exc()
        with Session() as db:
            obj=db.get(Trial,ident)
            if obj:obj.status='failed';obj.error=str(e);db.commit()
