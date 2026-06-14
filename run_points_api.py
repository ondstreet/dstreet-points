from flask import Flask
from web.api.points_api import points_bp
import os

app = Flask(__name__)
# Tell the points blueprint where the database is
os.environ['POINTS_DB_PATH'] = os.path.join(os.getcwd(), 'data', 'points.db')
app.register_blueprint(points_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
