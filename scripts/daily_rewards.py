# scripts/daily_rewards.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask
from core.points_models import db, UserPoints, RewardLog, TransactionType
from datetime import datetime, timedelta

# Create a minimal Flask app to use the models
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///points.db'  # match your actual URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

def distribute_mining_rewards():
    """Give every active user 1 point per day (mining reward)."""
    with app.app_context():
        users = UserPoints.query.all()
        for user in users:
            user.balance += 1
            user.lifetime_earned += 1
            log = RewardLog(
                user_id=user.user_id,
                amount=1,
                reason="Daily mining reward",
                transaction_type=TransactionType.REWARD
            )
            db.session.add(log)
        db.session.commit()
        print(f"Distributed mining rewards to {len(users)} users at {datetime.utcnow()}")

if __name__ == "__main__":
    distribute_mining_rewards()