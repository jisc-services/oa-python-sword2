"""
Deals with requests to the Col-IRI

Only POST and GET requests for the Col-IRI are supported.
(DELETE could be added as admin functionality, but it's not part of the SWORD spec).

POST: Create a collection
GET: Retrieve a collection
"""
from sword2.models import Entry
from sword2.server.controllers.mapper import SwordRequest
from sword2.server.util import atom_error


class CollectionRequest(SwordRequest):

    valid_methods = [
        "POST",
        "GET"
    ]

    @classmethod
    def _deposit_metadata(cls, request, collection, slug):
        """
        Metadata deposit handler. Creates an entry out of the request data and deposits it.

        :param request: Request object
        :param collection: Collection object
        :param slug: Slug header value

        :return: RepoContainer type of object or None if container can't be created (unlikely)
        """
        if request.data:
            return collection.deposit_metadata(Entry(request.data), slug)
        else:
            atom_error(cls.message("DATA_WAS_NOT_XML_ERROR"), 400)

    @classmethod
    def _deposit_binary(cls, request, collection, slug):
        """
        Binary deposit handler. Gets the file from the request body or form data if possible.

        :param request: Request object
        :param collection: Collection object
        :param slug: Slug header value

        :return: RepoContainer type of object or None if container can't be created (unlikely)
        """
        container = None
        stream, filename = cls._get_file_from_request(request)
        if stream and filename:
            container = collection.deposit_binary(stream, filename, slug)
        if not container:
            atom_error(cls.message("NO_FILE_ERROR"), 400)
        return container

    @classmethod
    def _deposit_multipart(cls, request, collection, slug):
        """
        Multipart deposit handler. Looks for an atom and payload file in the form data and deposits if possible.

        :param request: Request object
        :param collection: Collection object
        :param slug: Slug header value

        :return: RepoContainer type of object or None if container can't be created (unlikely)
        """
        atom = request.files.get("atom")
        payload = request.files.get("payload")
        if atom and payload:
            # If both of these files exist, do a multipart (both) deposit.
            return collection.deposit_metadata_and_file(atom.read(), payload, payload.filename, slug)
        else:
            atom_error(cls.message("BAD_MULTIPART_ERROR"), 400)

    @classmethod
    def get(cls, request, collection):
        """
        GET endpoint for collections

        :param request: Request object
        :param collection: Collection object

        :return: atom:feed of containers
        """
        return collection.to_feed(), 200

    @classmethod
    def post(cls, request, collection):
        """
        POST endpoint for collections

        :param request: Request object
        :param collection: Collection object

        :return: RepoContainer type of object or None if container can't be created (unlikely)
        """
        slug = request.headers.get("Slug")
        # If this is an XML document, deposit metadata.
        if cls._is_atom_xml(request):
            container = cls._deposit_metadata(request, collection, slug)
        # If there is an atom file, it's likely an attempt at a multipart deposit.
        elif request.files.get("atom"):
            container = cls._deposit_multipart(request, collection, slug)
        else:
            container = cls._deposit_binary(request, collection, slug)
        if request.headers.get("In-Progress", "false") == "false":
            container.complete_deposit()
        return container, 201
