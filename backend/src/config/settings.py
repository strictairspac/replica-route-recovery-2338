import os
DATABASE_URL=os.getenv('DATABASE_URL','mysql+pymysql://replicaroute:replicaroute_demo_pw@localhost:17747/replicaroute')
REDIS_URL=os.getenv('REDIS_URL','redis://redis:6379/0')
JWT_SECRET=os.getenv('JWT_SECRET','local-replica-route-change-before-public-use')
