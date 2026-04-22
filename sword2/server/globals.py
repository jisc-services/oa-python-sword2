"""
Data that needs to be available during flask requests.

'get_repository' is used to retrieve a user defined Repository (sword2.server.repository) implementation.
    This is used as the model for SWORD2 related requests.

'get_auth_instance' is used to retrieve a user defined SwordAuthBase (sword2.server.auth) implementation.
    This is used to authenticate every request to the SWORD2 server.

'get_messages_instance' is used to retrieve an instance of the Messages class (sword2.server.messages).
    This has user defined info messages to use when creating responses from the SWORD2 API.
"""
import os
from flask import current_app
from importlib import import_module
from werkzeug.local import LocalProxy

from sword2.server.messages import Messages


# Default directories and implementations for a sword server.
# These should be overridden by the config in current_app.
DEFAULT_BASE_DIR = os.path.expanduser("~/.sword2/repository")
DEFAULT_REPO_IMPL = "sword2.server.repository.FileRepository"
DEFAULT_AUTH_IMPL = "sword2.server.auth.SwordNoAuthentication"

REPO_KEY = "_S2_REPO"
AUTH_KEY = "_S2_AUTH"
MSGS_KEY = "_S2_MSGS"

def get_repository():
    """
    This uses the app's config to load and retrieve the implemented Repository class.

    :return: Repo object
    """
    # If repo is already part of the 'g' object, don't create it.
    # repo = getattr(g, 'repo', None)
    repo = current_app.config.get(REPO_KEY)
    if repo is None:
        repo_module_name, repo_class_name = current_app.config.get("REPO_IMPL", DEFAULT_REPO_IMPL).rsplit(".", 1)
        repo_class = getattr(import_module(repo_module_name), repo_class_name)
        # print(f"~~~Importing repo: '{repo_module_name}.{repo_class_name}'")
        # repo = g.repo = repo_class(*current_app.config.get("REPO_ARGUMENTS", [DEFAULT_BASE_DIR]))
        repo = current_app.config[REPO_KEY] = repo_class(*current_app.config.get("REPO_ARGUMENTS", [DEFAULT_BASE_DIR]))
    return repo


def get_messages_instance():
    """
    This loads the Sword messages class, replacing predefined messages with any alternatives that are provided in
    current_app.config.

    The instantiated Messages object is then stored in current_app.config.

    :return: message object
    """
    messages = current_app.config.get(MSGS_KEY)     # Obtain already instantiated Messages object if it exists
    if messages is None:
        # print(f"~~~Importing 'messages'")
        messages = current_app.config[MSGS_KEY] = Messages()
    return messages


def get_auth_instance():
    """
    This loads the implemented auth class that is referred to in the current_app's config.  The resulting object
    is then stored in current_app.config.

    :return: auth object
    """
    auth = current_app.config.get(AUTH_KEY)     # Obtain already instantiated Authentication object if it exists
    if auth is None:
        auth_module_name, auth_class_name = current_app.config.get("AUTH_IMPL", DEFAULT_AUTH_IMPL).rsplit(".", 1)
        auth_class = getattr(import_module(auth_module_name), auth_class_name)
        # print(f"~~~Importing auth: '{auth_module_name}.{auth_class_name}'")
        auth = current_app.config[AUTH_KEY] = auth_class
    return auth


# LocalProxy means these result in an error if accessed outside of an app_context. Inside, they will be available.
# http://flask.pocoo.org/docs/0.12/appcontext/
messages = LocalProxy(get_messages_instance)
repository = LocalProxy(get_repository)
auth = LocalProxy(get_auth_instance)
