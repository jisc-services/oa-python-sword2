"""
Utility methods that are used in the views
"""
from datetime import datetime
from flask import abort, make_response

from sword2.models import ErrorDocument
from sword2.server.globals import messages


@classmethod
def raise_not_implemented_error_for_method(cls, method_name):
    """
    Raise a NotImplementedError related to the given CLASS object and the method name of the function.

    This should be added onto classes like so:

    ---
    class Example():

        raise_not_implemented_error = raise_not_implemented_error_for_method
    ---

    Function works ONLY within a class.

    :param cls: Class object to pass use in string
    :param method_name: Method name of the executing function
    """
    raise NotImplementedError(
        f"Method '{method_name}' must be implemented in class '{cls.__name__}' before execution."
    )


def atom_response(model, status=200, headers=None):
    """
    Simple atom response for use with any of the models.

    :param model: SwordModel derivative to send as a response
    :param status: Status code to send
    :param headers: Any extra headers to send with the response

    :return: the string data of the SwordModel, the status code and the headers (correct order for a flask response)
    """
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/atom+xml; charset=utf-8"
    return str(model), status, headers


def atom_error(reason, status=404, verbose=None):
    """
    Error response for atom documents - will also abort a request.

    :param reason: String - Reason to insert into the ErrorDocument
    :param verbose: String - Optional long description of error to insert into the ErrorDocument
    :param status: Error code to give the error response. Defaults to 404 Not Found.
    """
    error = ErrorDocument()
    error.summary = reason
    if verbose:
        error.verbose = verbose
    headers = {
        "Content-Type": "application/atom+xml; charset=utf-8"
    }
    abort(make_response(str(error), status, headers))


def get_container_or_error(repository, collection_id, container_id):
    """
    Simple utility function to attempt to get a container, given a repository, a collection id and a container id.

    :param repository: Repository implementation
    :param collection_id: Collection id
    :param container_id: Container id

    :return: Container object (derived from RepoContainer); or will throw a 404 error if container DOESN'T exist.
    """
    collection = repository.get_collection(collection_id)
    container = None
    if collection:
        container = collection.get_container(container_id)
    if not container:
        atom_error(messages.ATOM_ERROR.format(container_id, collection_id))
    return container


def now_to_date_string():
    """
    Return the time as an iso formatted date string, like "2024-10-02T17:12:47Z"

    :return: ISO formatted date string of the current time.
    """
    return datetime.today().isoformat(timespec='seconds') + "Z"
