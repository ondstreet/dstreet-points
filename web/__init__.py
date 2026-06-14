from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from core.points_models import db
from web.routes.points import points_bp
from apscheduler.schedulers.background import BackgroundScheduler
from core.points_models import distribute_mining_rewards

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///points.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Register blueprint
app.register_blueprint(points_bp)

# Create tables
with app.app_context():
    db.create_all()

# Schedule daily mining rewards using APScheduler
scheduler = BackgroundScheduler()
scheduler.add_job(func=distribute_mining_rewards, trigger="cron", hour=0, minute=1)
scheduler.start()

# Optional: shut down scheduler on app exit
import atexit
atexit.register(lambda: scheduler.shutdown())


if __name__ == '__main__':
    app.run(debug=True)