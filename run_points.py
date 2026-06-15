from flask import Flask, render_template
from points_service.points_api import points_bp
from web.api.community_api import community_bp
import os

app = Flask(__name__)

os.makedirs('data', exist_ok=True)

# Register blueprints
app.register_blueprint(points_bp)
app.register_blueprint(community_bp, url_prefix='/api/community')

@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template('points_dashboard.html')

# Create community tables if not exist (optional)
with app.app_context():
    from core.models.community import Base
    from sqlalchemy import create_engine
    import os
    db_path = os.path.join(os.getcwd(), 'data', 'points.db')
    engine = create_engine(f'sqlite:///{db_path}')
    Base.metadata.create_all(engine)

if __name__ == '__main__':
    app.run()
