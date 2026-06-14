from flask import Flask
from web.api.points_api import points_bp

app = Flask(__name__)
app.register_blueprint(points_bp)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
