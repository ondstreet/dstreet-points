from flask import Flask, render_template
from points_service.points_api import points_bp
from web.api.community_api import community_bp

app = Flask(__name__)

app.register_blueprint(points_bp)
app.register_blueprint(community_bp)

@app.route('/')
@app.route('/dashboard')
def dashboard():
    return render_template('points_dashboard.html')

if __name__ == '__main__':
    app.run(debug=True, port=5000)