"""
Edit/Sword-Edit handler.

Deals with all Edit-IRI (The Atom Entry Edit IRI) and SE-IRI (SWORD Edit iri) requests.

IMPORTANT: This implementation of SWORD2 Server uses IDENTICAL URLs for Edit-IRI and SE-IRI (which is allowed by the
SWORD v2 specification)

GET: Get metadata from container
PUT: (a) Replace metadata; (b) Replace metadata + File content via a Multipart request; (c) complete deposit.
POST: (a) Update metadata; (b) Update metadata + Add new file content via Multipart request; (c) complete deposit.
DELETE: Delete the container.
"""
from sword2.server.controllers.mapper import SwordRequest, in_progress_wrapper
from sword2.server.util import atom_error


class EditRequest(SwordRequest):

    valid_methods = [
        "POST",
        "PUT",
        "GET",
        "DELETE"
    ]

    @classmethod
    def _deposit_multipart(cls, request, container, should_replace_metadata=False):
        """
        Complete a multipart deposit.

        Simply replace the metadata and the payload data.

        If both files do not exist, simply return None.

        :param request: Flask request
        :param container: Entry data
        :param should_replace_metadata: Whether we should update the metadata (POST) or replace the metadata (PUT)

        :return: Container or None
        """
        atom = request.files.get("atom")
        payload = request.files.get("payload")
        if atom and payload:
            container.add_or_replace_binary_file(payload, payload.filename)
            if should_replace_metadata:
                container.add_or_replace_metadata(atom.read())
            else:
                container.update_metadata(atom.read())
            return container
        return None

    @classmethod
    @in_progress_wrapper()
    def post(cls, request, container):
        """
        POST request to the Edit/SE iri - This ADDS Metadata and/or Content to existing container

        This has multiple options:
            Blank request with In-Progress == 'false' - Complete Deposit
            atom request - Update metadata
            Otherwise, check to see if we have a file with key 'atom' in request.files - multipart request

        If none of these match, abort with a NO_FILE_ERROR.

        :param request: Flask request
        :param container: Container for this deposit

        :return: container data or various error responses.
        """
        status = 201
        _container = None
        if request.headers.get("In-Progress") == "false" and not (request.data or request.files):
            _container = container
            status = 200
        elif cls._is_atom_xml(request):
            container.update_metadata(request.data)
            _container = container
        elif request.files or request.data:
            if request.files.get("atom"):
                _container = cls._deposit_multipart(request, container)
        if _container is None:
            atom_error(cls.message("NO_FILE_ERROR"), 400)
        return _container, status

    @classmethod
    @in_progress_wrapper()
    def put(cls, request, container):
        """
        PUT request - REPLACES metadata and/or files - fewer options than POST
            - ATOM request - replace metadata
            - Multipart request - replace metadata AND binary file

        Replacing just binary files is achieved via Edit-Media iri

        :param request: Flask request
        :param container: Container for this deposit.

        :return: 204 NO CONTENT on success, otherwise various error responses.
        """
        if cls._is_atom_xml(request):
            container.add_or_replace_metadata(request.data)
        elif request.files.get("atom"):
            cls._deposit_multipart(request, container, True)
        else:
            atom_error(cls.message("NO_FILE_ERROR"), 400)
        return '', 204

    @classmethod
    def get(cls, request, container):
        """
        Get metadata for this deposit.

        :param request: Flask request
        :param container: Container for this deposit.

        :return: Entry data for this deposit
        """
        return container, 200

    @classmethod
    def delete(cls, request, container):
        """
        Simply delete this container.

        :param request: Flask request
        :param container: Container for this deposit

        :return: 204 NO CONTENT or possible 500 internal server error if delete goes wrong.
        """
        container.delete()
        return '', 204
