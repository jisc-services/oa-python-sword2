"""
Simple Flask application implementation if wanting to use the sword2 server as a standalone app
"""
import os
from flask import Flask

app = Flask(__name__)
app.config.from_pyfile(os.path.realpath(os.path.expanduser("~/.sword2/sword.cfg")), silent=True)


# Simply add the sword blueprint to the app - can also be used with other applications.
def init_app(app):
    # In-line import as you may need the app's config but may not
    # need the blueprint.
    from sword2.server.views.blueprint import sword
    app.register_blueprint(sword)
