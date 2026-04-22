"""
Has a couple of utility classes for the sword client

SwordEncoder - MultipartEncoder from requests_toolbelt but changes the content type to multipart/related
guess_type - Guess the mimetype of a file
SwordException - Simple exception class that can be thrown during errors
"""
from requests_toolbelt import MultipartEncoder
from requests.exceptions import RequestException, ReadTimeout
from sword2.server.multipart import inject_into_werkzeug

inject_into_werkzeug()

class SwordEncoder(MultipartEncoder):

    @property
    def content_type(self):
        """
        This is the same as the default MultipartEncoder from requests toolbelt - the only difference is that
        it will use multipart/related instead of multipart/form-data.
        """
        return f'multipart/related; type="application/atom+xml"; boundary={self.boundary_value}'


class SwordException(RequestException):
    """
    Simple sword exception that adds the request and response objects as variables
        as they could be useful in debugging.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


def error_on_timeout(func):
    """
    Decorator used to wrap a function that expects a python requests timeout error, and instead throw a SwordException.

    :param func: Function to wrap, Should have a chance of throwing a requests.exceptions.ReadTimeout error.
    """
    def wrapper(self, *args, **kwargs):
        try:
            result = func(self, *args, **kwargs)
        except ReadTimeout as e:
            raise SwordException(f"ERROR: Request timed out after {self.timeout} seconds.", request=e.request)
        return result
    return wrapper
