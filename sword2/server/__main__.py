"""
Simplistic main function to run the server as a module.

Adds the sword blueprint with init_app and then runs the server.
"""
from sword2.server.app import app, init_app

init_app(app)

app.run(debug=app.config.get("DEBUG", False))
