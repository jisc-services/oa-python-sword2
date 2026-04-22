"""
This class holds a couple of fixes for werkzeug to do with multipart/related requests.

The default multipart/form-data parser for werkzeug will easily parse a multipart/related request,
the problem is that by default it will not attempt to parse it.
"""
from werkzeug.wrappers import Request
from werkzeug.formparser import FormDataParser

class MultipartRelatedFormDataParser(FormDataParser):

    def parse(self, stream, mimetype, content_length, options=None,):
        """Parses the information from the given stream, mimetype,
        content length and mimetype parameters.

        :param stream: an input stream
        :param mimetype: the mimetype of the data
        :param content_length: the content length of the incoming data
        :param options: optional mimetype parameters (used for
                        the multipart boundary for instance)
        :return: A tuple in the form ``(stream, form, files)``.

        ::version changed:: 3.0
            The invalid ``application/x-url-encoded`` content type is not
            treated as ``application/x-www-form-urlencoded``.
        """
        if mimetype == "multipart/form-data":
            parse_func = self._parse_multipart
        elif mimetype == "multipart/related":
            parse_func = self._parse_multipart
        elif mimetype == "application/x-www-form-urlencoded":
            parse_func = self._parse_urlencoded
        else:
            return stream, self.cls(), self.cls()
        if options is None:
            options = {}

        try:
            return parse_func(stream, mimetype, content_length, options)
        except ValueError:
            if not self.silent:
                raise

        return stream, self.cls(), self.cls()

# Simple function that is used on init of this module - just sets the static variable of the form parser class
# in werkzeug to use the new form data parser.
def inject_into_werkzeug():
    Request.form_data_parser_class = MultipartRelatedFormDataParser
