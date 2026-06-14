# scripts/distribute_mining_rewards.py
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from flask import Flask
from core.points_models import db, UserPoints, RewardLog, TransactionType
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///points.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def distribute_mining_rewards():
    with app.app_context():
        users = UserPoints.query.all()
        for user in users:
            user.balance += 1
            user.lifetime_earned += 1
            log = RewardLog(user_id=user.user_id, amount=1, reason="Daily mining reward", transaction_type=TransactionType.REWARD)
            db.session.add(log)
        db.session.commit()
        print(f"Mining rewards distributed at {datetime.utcnow()}")

if __name__ == "__main__":
    distribute_mining_rewards()