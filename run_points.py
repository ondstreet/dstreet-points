from flask import Flask, render_template
from points_service.points_api import points_bp
from web.api.community_api import community_bp
# from core.api.feedback_api import feedback_api as feedback_bp   # <-- COMMENT OUT
import os

app = Flask(__name__)

# Ensure data directory exists
os.makedirs('data', exist_ok=True)

# Register blueprints
app.register_blueprint(points_bp)
app.register_blueprint(community_bp, url_prefix='/api/community')
# app.register_blueprint(feedback_bp, url_prefix='/api/feedback')   # <-- COMMENT OUT

# ----- HTML page routes -----
@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template('points_dashboard.html')

@app.route('/community/bugs')
def community_bugs():
    return render_template('community/bugs.html')

@app.route('/community/bounties')
def community_bounties():
    return render_template('community/bounties.html')

@app.route('/community/dashboard')
def community_dashboard():
    return render_template('community/dashboard.html')
# ----------------------------

# ----- Safe route printer (skips dynamic endpoints) -----
def print_static_routes():
    BASE_URL = "http://127.0.0.1:5000"
    print("\n" + "="*70)
    print("🌐 HTML PAGES (clickable)")
    print("="*70)
    seen_urls = set()
    with app.test_request_context():
        for rule in app.url_map.iter_rules():
            # Only include routes that serve HTML pages (not /api/...)
            if rule.rule.startswith('/api/'):
                continue
            if rule.arguments:
                continue
            if rule.endpoint == 'static':
                continue
            methods = ','.join(rule.methods - {'HEAD', 'OPTIONS'})
            url = f"{BASE_URL}{rule.rule}"
            if url in seen_urls:
                continue
            seen_urls.add(url)
            print(f"{methods:15} {url}")
    print("="*70 + "\n")

# Create tables and print static routes
with app.app_context():
    from sqlalchemy import create_engine
    from core.models.points import Base as PointsBase
    from core.models.community import Base as CommunityBase
    from core.models.points import UserPoints, Stake, Proposal, Vote, RewardLog
    from core.models.community import BugReport, Bounty, UserCommunityStats, NameRegistry

    db_path = os.path.join(os.getcwd(), 'data', 'points.db')
    engine = create_engine(f'sqlite:///{db_path}')
    PointsBase.metadata.create_all(engine)
    CommunityBase.metadata.create_all(engine)

    print_static_routes()

if __name__ == '__main__':
    app.run()
