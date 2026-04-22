"""
Default request mapper.

This maps SWORD IRIs to controller functions.
"""
from functools import wraps
from io import BytesIO
from lxml.etree import XMLSyntaxError
from flask import current_app

from sword2.server.exceptions import RepositoryError
from sword2.server.globals import messages
from sword2.server.util import atom_error

####  parse_header originally in Python CGI, but was removed
def parse_header(line):
    """Parse a Content-type like header.

    Return the main content-type and a dictionary of options.

    """
    def _parseparam(s):
        while s[:1] == ';':
            s = s[1:]
            end = s.find(';')
            while end > 0 and (s.count('"', 0, end) - s.count('\\"', 0, end)) % 2:
                end = s.find(';', end + 1)
            if end < 0:
                end = len(s)
            f = s[:end]
            yield f.strip()
            s = s[end:]

    parts = _parseparam(';' + line)
    key = parts.__next__()
    pdict = {}
    for p in parts:
        i = p.find('=')
        if i >= 0:
            name = p[:i].strip().lower()
            value = p[i+1:].strip()
            if len(value) >= 2 and value[0] == value[-1] == '"':
                value = value[1:-1]
                value = value.replace('\\\\', '\\').replace('\\"', '"')
            pdict[name] = value
    return key, pdict


class SwordRequest:

    valid_methods = [
        "POST",
        "GET",
        "PUT",
        "DELETE"
    ]

    def __init__(self, method):
        """
        :param method: One of "GET", "POST".

        Simply get the correct function for the given method.

        In the view, the methods will be one of the ones in valid_requests above. These should be implemented
            on child classes.
        """
        self.method = self._map_method(method)

    @classmethod
    def _map_method(cls, method):
        """
        :param method: One of "GET", "POST".

        Map a method ("POST", "GET" etc.) to a request function

        :return: function to be used by __call__
        """
        if method not in cls.valid_methods:
            raise ValueError(f"{cls.__name__} cannot process a {method} request")
        return getattr(cls, method.lower())

    @classmethod
    def _is_atom_xml(cls, request):
        """
        Given a request, figure out whether it's an atom xml request.

        Make sure the mimetype (value) ends with xml.

        :param request: Flask request
        :return: Whether the content type is an XML content type
        """
        ctype = request.content_type or "application/atom+xml"
        mimetype, _ = parse_header(ctype)
        return mimetype.endswith("atom+xml")

    @classmethod
    def _get_file_from_request(cls, request):
        """
        If we need to get a filename and file stream, first check whether it's a multipart (request.files) file.
        If not, get the filename from the Content-Disposition header and create a stream out of the request data.

        :param request: Flask Request
        :return: Tuple of stream and filename, or both None if there is no file or filename.
        """
        stream = None
        filename = None
        if request.files:
            stream = request.files.get("attachment")
            if stream:
                filename = stream.filename
        else:
            disposition = request.headers.get("Content-Disposition")
            if disposition:
                stream = BytesIO(request.data)
                value, params = parse_header(disposition)
                filename = params.get("filename")
        return stream, filename

    @classmethod
    def message(cls, message_attr):
        """
        Get a message string using the message object.

        If message_attr is not an attribute of messages, will throw an error, but note that the default implementation
        only uses defined messages (so it won't throw an error by default.)

        :return: Message string.
        """
        return getattr(messages, message_attr)

    def __call__(self, *args, **kwargs):
        """
        *args and **kwargs allow for the actual request functions (get, post etc.) to have more arguments if needed
            on other controllers.

        On an XMLSyntaxError (bad data) or a RepositoryError (suggests a repository model failure),
        respond with an error.

        :return: Tuple of data to do with this request
        """
        try:
            data_tuple = self.method(*args, **kwargs)
        except XMLSyntaxError:
            atom_error(self.message("DATA_WAS_NOT_XML_ERROR"), 400)
        except RepositoryError as e:
            if e.log_level:
                current_app.logger.log(
                    e.log_level,
                    f"{e.message}" + (f" - {e.verbose_msg}" if e.verbose_msg else "") + (f"\n - {e.log_msg}" if e.log_msg else ""))
            atom_error(e.message, e.status_code, e.verbose_msg)
        return data_tuple

    @classmethod
    def get(cls, request, model):
        pass

    @classmethod
    def post(cls, request, model):
        pass

    @classmethod
    def put(cls, request, model):
        pass

    @classmethod
    def delete(cls, request, model):
        pass


def in_progress_wrapper():
    """
    A wrapper used to finish processing if the In-Progress header is not true.

    For anything that handles a container (entry), will finish container processing if the header does not imply
        any more data should be received.

    :return: decorator for in progress header
    """
    def decorator(func):
        @wraps(func)
        def wrapper(model_request, flask_request, entry, *args, **kwargs):
            func_result = func(model_request, flask_request, entry, *args, **kwargs)
            if entry.in_progress and flask_request.headers.get("In-Progress", 'false') == 'false':
                entry.complete_deposit()
            return func_result
        return wrapper
    return decorator
