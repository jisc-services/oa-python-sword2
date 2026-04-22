"""
Edit media controller.

Deals with all EM-IRI (Edit Media) and Cont-IRI (Content IRI) requests.

GET: (a) Retrieve the all content of container as a package; (b) Retrieve specified resource (file) from the container.
POST: (a) Add individual file (binary content); (b) Add several files from a package (zipfile) to the container
PUT: (a) Replace individual file (binary content); (b) Replace all files from a package (zipfile) in the container
DELETE: Delete binary content (file) from the container (but NOT delete the container itself)
"""
# from werkzeug.wsgi import wrap_file
from flask import stream_with_context
from sword2.server.controllers.mapper import SwordRequest, in_progress_wrapper
from sword2.server.util import atom_error


class EditMediaRequest(SwordRequest):

    valid_methods = [
        "POST",
        "PUT",
        "GET",
        "DELETE"
    ]

    @classmethod
    @in_progress_wrapper()
    def post(cls, request, container, filename=None):
        """
        Deal with an EM-IRI/Cont-IRI POST request. This request adds binary content to a deposit:
            (a) Add individual file (binary content);
            (b) Add several files from a package (zipfile) to the container

        :param request: Flask request
        :param container: RepoContainer derivative
        :param filename: Filename passed to the request

        :return: Container object with a 201 status code if successful, 400 if there is no attachment file
        """
        if filename:
            stream, _ = cls._get_file_from_request(request)
        else:
            stream, filename = cls._get_file_from_request(request)
        if stream and filename:
            container.add_or_replace_binary_file(stream, filename)
        else:
            atom_error(cls.message("NO_FILE_ERROR"), 400)
        return container, 201

    @classmethod
    @in_progress_wrapper()
    def put(cls, request, container, filename=None):
        """
        Deal with an EM-IRI/Cont-IRI PUT request.

        This request replaces:
         (a) replaces an individual binary file in the container; or
         (b) replaces all binary files in container if a package (ZipFile) is sent

        This is a bit more permissive than default sword as it will simply run what the post request would do if
        you don't put a filename.

        :param request: Flask request
        :param container: RepoContainer derivative
        :param filename: Filename passed to the request

        :return: blank data with a 204 status code if successful, 400 if there is no attachment file
        """
        cls.post(request, container, filename)
        return '', 204

    @classmethod
    def get(cls, request, container, filename=None):
        """
        GET binary data.

        Will attempt to get the data from the store, and it will also wrap the content so it can be streamed
        (rather than having to load the file into memory with file.read).

        :param request: Flask request
        :param container: RepoContainer derivative
        :param filename: Filename passed to the request

        :return: data file stream if found, otherwise 404
        """
        file_stream = container.get_file_content(filename) if filename else container.get_all_file_content_as_zip()
        # if file_stream:
        #     # This will make a wrapper for the file that can be streamed, to avoid loading it all into memory
        #     data = wrap_file(request.environ, file_stream)
        # if not data:
        if not file_stream:
            atom_error(cls.message("DID_NOT_FIND_FILE_ERROR").format(filename))
        return stream_with_context(file_stream), 200

    @classmethod
    def delete(cls, request, container, filename=None):
        """
        DELETE binary content (file) from the container (but NOT delete the container itself)

        :param request: Flask request
        :param container: RepoContainer derivative
        :param filename: Filename passed to the request

        If it is not successful (filename was not found), 404.

        :return: blank data with 204 status code or 404 if no file found
        """
        successful = container.delete_content(filename)
        if not successful:
            atom_error(cls.message("DID_NOT_FIND_FILE_ERROR").format(filename))
        return '', 204
