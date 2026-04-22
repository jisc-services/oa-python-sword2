"""
To fix issues with multipart/related, we need to tell werkzeug (underlying part of Flask)
to use the multipart/formdata parser for multipart/related.

This is done using the code in sword2.server.multipart.
"""
from sword2.server.multipart import inject_into_werkzeug

inject_into_werkzeug()
