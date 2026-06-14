import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.models.points import UserPoints, RewardLog
from datetime import datetime

from points_service.points_api import get_db_session, get_user_points, RewardLog

engine = create_engine('sqlite:///data/points.db')
Session = sessionmaker(bind=engine)
session = get_db_session()
users = session.query(UserPoints).all()
for user in users:
    user.balance += 1
    user.lifetime_earned += 1
    log = RewardLog(user_id=user.user_id, amount=1, reason="Daily mining reward")
    session.add(log)
session.commit()
session.close()
print(f"Mining rewards distributed at {datetime.utcnow()}")