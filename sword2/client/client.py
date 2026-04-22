"""
File for the main SwordClient - has methods to that will interact with a SWORD2 Server

The functions public API is as follows:

    - get_service_document: Retrieve the service document for the server
    - multipart_deposit: Make a full multipart deposit (metadata + file)
    - replace_multipart_deposit: Make a multipart deposit with the intention of replacing files and metadata
    - add_multipart_deposit: Make a multipart deposit with the intention of adding files and metadata
    - metadata_deposit: Make an initial deposit with some metadata atom entries
    - replace_metadata: Replace the metadata of a deposit
    - add_metadata: Add new metadata to a deposit
    - file_deposit: Make an initial deposit with a binary package/file
    - add_file: Add file content to a deposit
    - replace_file: Replace file content of a deposit
    - get_content: Retrieve original content from a deposit (like zip files)
    - get_file: Retrieve a file from a deposit
    - delete_all_content: Delete ALL file content of a deposit
    - delete_file: Delete a specific files from a deposit
    - delete_deposit: Delete the entire deposit
    - complete_deposit: Send a complete deposit request

For more information read the README.md at the base of the project.
"""
import requests
from functools import partial
from lxml.etree import XMLSyntaxError
from requests.auth import HTTPBasicAuth
from urllib.parse import urljoin, urlparse

from sword2.client.util import SwordEncoder, SwordException, error_on_timeout
from sword2.models import DepositReceipt, ErrorDocument, ServiceDocument, SwordModel, guess_type


class SwordClient:

    DEFAULT_PACKAGING = "http://purl.org/net/sword/package/SimpleZip"
    # The 'Col' and 'SD' IRIs are defined in the __init__ method.
    # The 'Edit', 'EM' and 'SE' IRIs are returned in the DepositReceipts.
    # Note that the 'Content' and 'EM' IRIs are interchangeable.

    def __init__(self, base_collection_iri, auth_credentials=None, **kwargs):
        """
        Init with the base of the sword location and collection_iri.
        Collection_iri is required as without it you can't really do much.

        :param base_collection_iri: Col-IRI - collection endpoint of sword2 server (e.g.: id/contents for eprints)
        :param auth_credentials: {"username": "", "password": ""} BASIC auth object
        :param kwargs:
            service_document_iri: SD-IRI - service document IRI
            receipt_class: Custom receipt class if wanted. EPrints for example, has custom receipts if using an
                <eprint> style deposit.
            timeout: Timeout for requests. Defaults to 120 seconds (2 minutes)
        """
        self.base_collection_iri = base_collection_iri
        self.service_document_iri = kwargs.pop("service_document_iri", None)
        self.receipt_class = kwargs.pop("receipt_class", DepositReceipt)
        self.timeout = kwargs.pop("timeout", 120)
        self.auth_credentials = None
        if auth_credentials is not None:
            self.auth_credentials = HTTPBasicAuth(auth_credentials.get("username"), auth_credentials.get("password"))

    def get_service_document(self):
        """
        If we have a SD-IRI, request it then make a ServiceDocument model out of it.

        :return: ServiceDocument model of request data. Will throw an exception if service document IRI is not set.
        """
        if not self.service_document_iri:
            raise SwordException("Service document IRI does not exist.")
        response = self._get_response(self.request(self.service_document_iri))
        return ServiceDocument(response.content)

    def _send_data(self, request_partial, headers, **kwargs):
        """
        Helper function for sending data (binary, package, XML metadata) to a sword2 server.

        :param request_partial: Request partial made from self.request - A function that returns a response.
        :param headers: Dict of headers
        :param kwargs:
            files: File tuples for use with requests (filename, file-byte-stream, content-type)
            data: String data or file stream. Can be any sort of data (file content, XML metadata).
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
        :return: On success, return a DepositReceipt if we receive XML data or None otherwise.
            If there is a failure, return an ErrorDocument.

        Will raise a SwordException if the request data is not XML.
        """
        try:
            in_progress = "true" if kwargs.pop("in_progress", None) else "false"
            headers["In-Progress"] = in_progress
            data = kwargs.get("data")
            if data and isinstance(data, SwordModel):
                # If this is a SwordModel, cast it into string data rather than the class instance
                kwargs["data"] = bytes(data)
            kwargs["headers"] = headers
            # Execute request partial
            response = self._get_response(request_partial, **kwargs)
            text = response.content
            receipt = None
            # True if HTTP response code is of form 2xx
            status_ok = response.status_code // 100 == 2
            if text:
                # Make a receipt instance if the status_code is 2xx, otherwise an ErrorDocument
                receipt = self.receipt_class(text) if status_ok else ErrorDocument(text)

                # If we have a location, add it to the receipt
                location = response.headers.get("Location")
                if location:
                    receipt.location = location
            else:
                # if not 2xx
                if not status_ok:
                    receipt = ErrorDocument()
                    receipt.summary = "ERROR: Unknown error from server"

        except XMLSyntaxError:
            raise SwordException("ERROR: the server returned malformed xml or a webpage.", response=response)
        return receipt

    @error_on_timeout
    def _get_response(self, request_partial, **kwargs):
        """
        Deal with redirects and make sure we get a response.

        Up to 10 redirects are allowed, after that an exception will be raised to prevent infinite redirect looping.

        :param request_partial: Request partial from self.request - A function that returns a response.
        :param kwargs: Kwargs that apply to the request - see Requests library

        :return: Request response
        """
        max_redirects = 10
        response = request_partial(**kwargs)
        # While response status code returns a redirect (3xx code)
        while response.status_code // 100 == 3:
            response = self._deal_with_https_redirect(response, kwargs)
            if max_redirects == 0:
                raise SwordException("ERROR: Request has a redirect loop")
            max_redirects -= 1
        return response

    def _deal_with_https_redirect(self, response, kwargs):
        """
        If there's a redirect, redo the redirect with the original request method.

        This uses urlparse and urljoin from urllib - documentation is here
        https://docs.python.org/3/library/urllib.parse.html

        :param response: Last response that was a redirect
        :param kwargs: Request kwargs that need to be reapplied

        :return: Response of new request
        """
        data = kwargs.get("data")
        if data:
            if hasattr(data, "seek"):
                # If we have been sending file data, the file pointer will have to be moved back to 0.
                data.seek(0)
        # Get redirection URL from Location header
        url = response.headers.get("Location")
        # Use requests urlparse function to get information about the url
        url_info = urlparse(url)
        # If URL is relative ("/abc/def") or schemeless ("//awebsite.website/abc/def")
        if not url_info.hostname or not url_info.scheme:
            url = urljoin(response.url, url)
        # Use same method as original request
        request_partial = self.request(url, response.request.method)
        return request_partial(**kwargs)

    def _create_collection_iri(self, collection_id=None):
        """
        Create a full Col-IRI

        :param collection_id: ID of collection.

        return: Correctly formatted collection IRI. if None or falsey, will return the original collection_iri
            (useful on things with only one collection like EPrints)
        """
        return f"{self.base_collection_iri}/{collection_id}" if collection_id else self.base_collection_iri

    def _add_or_replace_entry(self, request_partial, entry, **kwargs):
        """
        Set the correct headers for a request to add or replace an entry, and make the request.

        :param request_partial: request partial from self._request - A function that returns a response
        :param entry: Any child of sword2_cli.models.SwordModel or string XML data. Can also be an XML file stream.
        :param kwargs:
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            content_type: Specific content type in case the deposit requires something that isn't application/atom+xml
                (ex: eprints has its own specific content type for EPrints metadata)

        :return: Response from server
        """
        headers = {"Content-Type": kwargs.pop("content_type", "application/atom+xml; type=entry")}
        return self._send_data(request_partial, headers, data=entry, **kwargs)

    def _add_or_replace_file_deposit(self, request_partial, filename, stream, **kwargs):
        """
        Set the correct headers for a request to add or replace content, and make the request.

        :param request_partial: Request partial from self._request - A function that returns a response
        :param filename: filename
        :param stream: Stream like data
        :param kwargs:
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            packaging: Packaging URI or None
            content_type: A valid content-type of the file or None.

        This will guess the mimetype of the file from the filename - in cases where it is not guessable, it will
            be sent as binary safe data (application/octet-stream)

        :return: response from server
        """
        content_type = kwargs.pop("content_type", None) or guess_type(filename)
        headers = {
            "Content-Type": content_type,
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
        packaging = self._get_packaging(kwargs.pop("packaging", None), content_type)
        if packaging:
            headers["Packaging"] = packaging
        return self._send_data(request_partial, headers, data=stream, **kwargs)

    def _add_or_replace_multipart(self, request_partial, entry, filename, stream, **kwargs):
        """
        Set the correct headers for a multipart request, and make the request.

        The SwordEncoder object configures the request data correctly for a multipart/related request.

        Note that these multipart requests consists of entry metadata followed by a single content file.
        It is not possible to attach multiple files with a multipart request.

        The file can be a zip file or a content file, either is fine.

        :param request_partial: Request partial from self._request, A function that will return a response
        :param entry: Any child of sword2_cli.models.SwordModel or string data. Can also be a file stream.
        :param filename: filename
        :param stream: Stream like data
        :param kwargs:
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            packaging: Packaging URI or None
            content_type: valid content-type of the file or None.

        :return: response from server
        """
        content_type = kwargs.pop("content_type", None) or guess_type(filename)
        packaging = self._get_packaging(kwargs.pop("packaging", None), content_type)
        payload_headers = {"Packaging": packaging} if packaging else {}
        multipart = SwordEncoder({
            "atom": ("entry.xml", bytes(entry), "application/atom+xml"),
            "payload": (filename, stream.read(), content_type, payload_headers)
        })
        headers = {"Content-Type": multipart.content_type}
        return self._send_data(request_partial, headers, data=multipart, **kwargs)

    @staticmethod
    def _get_iri_from_kwargs(type_, kwargs):
        """
        Get an IRI from the 'iri' kwarg, otherwise attempt to get it from the receipt if there is one.

        :param type_: Type of IRI (like 'se_iri' or 'edit_iri')
        :param kwargs: Kwargs to look through. one of these is required - otherwise an error will be thrown.
            iri: Manually defined IRI in case someone does not have a DepositReceipt available but does have the IRI
            deposit_receipt: DepositReceipt object that will get whatever type of IRI needed from its own attributes

        :return: IRI if found, otherwise throw an error as we can't proceed without one.
        """
        iri = kwargs.pop(type_, None)
        if not iri:
            receipt = kwargs.pop("deposit_receipt", None)
            if receipt:
                iri = getattr(receipt, type_)
        if not iri:
            raise SwordException("ERROR: IRI not found in kwargs or deposit receipt")
        return iri

    def _get_packaging(self, packaging, content_type=None, filename=None):
        """
        If we have a zip file, set the packaging header to default packaging if we don't have one already.
        Note must have one of content_type or filename being not None.

        :param packaging: Packaging URI or None.
        :param content_type: File content-type or None.
        :param filename: filename or None

        :return: Packaging or default packaging if we need one
        """

        if not packaging and "application/zip" == (content_type or guess_type(filename)):
            packaging = self.DEFAULT_PACKAGING
        return packaging

    def multipart_deposit(self, entry, filename, stream, **kwargs):
        """
        Do a multipart deposit to a collection.

        If successful, the Edit-IRI, EM-IRI and SE-IRI will be returned in the DepositReceipt

        :param entry: Any child of sword2_cli.models.SwordModel or string XML data. Can also be an XML file stream.
        :param filename: Filename
        :param stream: Stream like data
        :param kwargs:
            packaging: Packaging URI if the file is a zip
            collection_id: If no collection_id specified, then the base Collection IRI will be used.
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)

        :return: DepositReceipt if available, else None
        """
        collection_id = kwargs.pop("collection_id", "")
        url = self._create_collection_iri(collection_id)
        request_partial = self.request(url, request_method="POST")
        return self._add_or_replace_multipart(request_partial, entry, filename, stream, **kwargs)

    def replace_multipart_deposit(self, entry, filename, stream, **kwargs):
        """
        Replaces both the metadata and the content with a given filename of the existing container identified
        by the EDIT-IRI.

        The Edit-IRI is obtained either from a prior request's DepositReceipt or may be specified by the 'iri' kwarg.

        :param entry: Any child of sword2_cli.models.SwordModel or string XML data. Can also be an XML file stream.
        :param filename: filename
        :param stream: Stream like data
        :param kwargs:
            packaging: Packaging URI if the file is a zip
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            iri: User defined EDIT-IRI
            deposit_receipt: Previous DepositReceipt that can retrieve the EDIT-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: None, unless erroring.
        """
        iri = self._get_iri_from_kwargs("edit_iri", kwargs)
        request_partial = self.request(iri, request_method="PUT")
        return self._add_or_replace_multipart(request_partial, entry, filename, stream, **kwargs)

    def add_multipart_deposit(self, entry, filename, stream, **kwargs):
        """
        Add multipart data to a container.

        This will attempt to add a new entry metadata and a new file in a deposit using the SE-IRI.

        :param entry: Any child of sword2_cli.models.SwordModel or string XML data. Can also be an XML file stream.
        :param filename: filename
        :param stream: Stream like data
        :param kwargs:
            packaging: Packaging URI if the file is a zip
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            iri: User defined SE-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the SE-IRI.
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: DepositReceipt if available, otherwise None
        """
        iri = self._get_iri_from_kwargs("se_iri", kwargs)
        request_partial = self.request(iri, request_method="POST")
        return self._add_or_replace_multipart(request_partial, entry, filename, stream, **kwargs)

    def file_deposit(self, filename, stream, **kwargs):
        """
        Deposit file content in an acceptable packing format, such as SimpleZip (common zip file),
        creating a new container (aka resource).

        :param filename: filename
        :param stream: Stream like data
        :param kwargs:
            packaging: Packaging URI if the file is a zip
            collection_id: Collection id if server needs one
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)

        :return: DepositReceipt if available, otherwise None
        """
        collection_id = kwargs.pop("collection_id", "")
        url = self._create_collection_iri(collection_id)
        request_partial = self.request(url, request_method="POST")
        return self._add_or_replace_file_deposit(request_partial, filename, stream, **kwargs)

    def add_file(self, filename, stream, **kwargs):
        """
        Add content to an existing container identified by the EM IRI(POST request).

        :param filename: filename
        :param stream: Stream like data
        :param kwargs:
            packaging: Packaging URI if the file is a zip
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            iri: User defined EM-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EM-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: DepositReceipt if available, otherwise None
        """
        iri = self._get_iri_from_kwargs("em_iri", kwargs)
        request_partial = self.request(iri, request_method="POST")
        return self._add_or_replace_file_deposit(request_partial, filename, stream, **kwargs)

    def replace_file(self, filename, stream, **kwargs):
        """
        Replace the content in an existing container identified by the EM IRI.

        :param filename: filename
        :param stream: Stream like data
        :param kwargs:
            packaging: Packaging URI if the file is a zip
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            iri: User defined EM-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EM-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: None, unless erroring
        """
        em_iri = self._get_iri_from_kwargs("em_iri", kwargs)
        iri = f"{em_iri}/{filename}"
        request_partial = self.request(iri, request_method="PUT")
        return self._add_or_replace_file_deposit(request_partial, filename, stream, **kwargs)

    def metadata_deposit(self, entry, **kwargs):
        """
        Deposit to a collection with XML metadata.

        :param entry: Any child of sword2_cli.models.SwordModel or string XML data. Can also be an XML file stream.
        :param kwargs:
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)
            collection_id: ID of collection
            content_type: Specific content type in case the deposit requires something that isn't application/atom+xml
                (ex: eprints has its own specific content type for EPrints metadata)

        :return: DepositReceipt if available, otherwise None
        """
        url = self._create_collection_iri(kwargs.pop("collection_id", ""))
        request_partial = self.request(url, request_method="POST")
        return self._add_or_replace_entry(request_partial, entry, **kwargs)

    def add_metadata(self, entry, **kwargs):
        """
        Add XML metadata to an existing container using the SE-IRI.

        :param entry: Any child of sword2_cli.models.SwordModel or string XML data. Can also be an XML file stream.
        :param kwargs:
            iri: User defined SE-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the SE-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)

        :return: DepositReceipt is available, otherwise None
        """
        iri = self._get_iri_from_kwargs("se_iri", kwargs)
        request_partial = self.request(iri, request_method="POST")
        return self._add_or_replace_entry(request_partial, entry, **kwargs)

    def replace_metadata(self, entry, **kwargs):
        """
        Replace the XML metadata content of a container using the Edit-IRI.

        :param entry: Any child of sword2_cli.models.SwordModel or string XML data. Can also be an XML file stream.
        :param kwargs:
            iri: User defined EDIT-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EDIT-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.
            in_progress: Indicates if further steps in a multistep deposit are expected (True) or
                whether this is the final part of a deposit (False, None)

        :return: None, unless erroring
        """
        iri = self._get_iri_from_kwargs("edit_iri", kwargs)
        request_partial = self.request(iri, request_method="PUT")
        return self._add_or_replace_entry(request_partial, entry, **kwargs)

    def _delete_content(self, filename=None, **kwargs):
        """
        Delete all file content or specific file in a container.

        :param filename: Filename to delete if wanting to delete a specific file
        :param kwargs:
            iri: User defined EM-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EM-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: True if successfully deleted, else False.
        """
        iri = self._get_iri_from_kwargs("em_iri", kwargs)
        if filename:
            iri = f"{iri}/{filename}"
        request_partial = self.request(iri, request_method="DELETE")
        response = self._get_response(request_partial)
        return response.status_code == 204

    def delete_all_content(self, **kwargs):
        """
        Delete all file content in a container using the EM-IRI.

        :param kwargs:
            iri: User defined EM-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EM-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: True if successfully deleted, else False.
        """
        return self._delete_content(**kwargs)

    def delete_file(self, filename, **kwargs):
        """
        Delete a specific file in a container.

        :param filename: Filename to delete if wanting to delete a specific file
        :param kwargs:
            iri: User defined EM-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EM-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: True if successfully deleted, else False.
        """
        return self._delete_content(filename, **kwargs)

    def delete_deposit(self, **kwargs):
        """
        Delete entire container using the EDIT-IRI.

        :param kwargs:
            iri: User defined EDIT-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EDIT-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: True if successfully deleted, else False
        """
        iri = self._get_iri_from_kwargs("edit_iri", kwargs)
        request_partial = self.request(iri, request_method="DELETE")
        response = self._get_response(request_partial)
        return response.status_code == 204

    def complete_deposit(self, **kwargs):
        """
        Send a complete deposit request using SE-IRI.
        This method should be used at the end of a multistep deposit process for example where metadata and file(s)
        have been added to a container using successive function calls with 'in_progress' parameter set to True.
        (Note that if a function was called with in_progress=False or where in_progress was not set,
        then this complete_deposit method is not needed).

        :param kwargs:
            iri: User defined SE-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the SE-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: Deposit receipt from deposit completion
        """
        iri = self._get_iri_from_kwargs("se_iri", kwargs)
        request_partial = self.request(iri, request_method="POST")
        headers = {
            "Content-Length": "0",
            "In-Progress": "false"
        }
        return self._send_data(request_partial, headers)

    def get_deposit_receipt_with_metadata(self, **kwargs):
        """
        Retrieve submitted metadata (in a deposit receipt) using the Edit-IRI.

        :param kwargs:
            iri: User defined Edit-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the Edit-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: DepositReceipt of the resulting request (includes Entry metadata)
        """
        iri = self._get_iri_from_kwargs("edit_iri", kwargs)
        request_partial = self.request(iri, request_method="GET")
        # Should contain a deposit receipt with metadata
        response = self._get_response(request_partial)
        content = None
        if response.status_code == 200:
            content = self.receipt_class(response.content)
        return content

    def get_content(self, packaging=None, **kwargs):
        """
        Retrieve the original deposit content from the server.
        These are returned in requested package format, which defaults to SimpleZip if none is specified.

        :param packaging: Packaging format
        :param kwargs:
            iri: User defined EM-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EM-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: Response content
        """
        iri = self._get_iri_from_kwargs("em_iri", kwargs)
        request_partial = self.request(iri, request_method="GET")
        packaging = packaging or self.DEFAULT_PACKAGING
        headers = {"Accept-Packaging": packaging}
        response = self._get_response(request_partial, headers=headers)
        content = None
        if response.status_code == 200:
            content = response.content
        return content

    def get_file(self, filename, packaging=None, **kwargs):
        """
        Retrieve a given file from the server.
        These are returned in requested package format, which defaults to SimpleZip if none is specified.

        :param filename: Name of file to retrieve
        :param packaging: Packaging URI or None
        :param kwargs:
            iri: User defined EM-IRI
            deposit_receipt: A DepositReceipt object that can retrieve the EM-IRI
            NOTE - only one of iri and deposit_receipt are needed. If both are given, iri is preferred.

        :return: response content
        """
        em_iri = self._get_iri_from_kwargs("em_iri", kwargs)
        iri = f"{em_iri}/{filename}"
        request_partial = self.request(iri, request_method="GET")
        headers = {}
        packaging = self._get_packaging(packaging, filename=filename)
        if packaging:
            headers = {"Accept-Packaging": packaging}
        response = self._get_response(request_partial, headers=headers)
        content = None
        if response.status_code == 200:
            content = response.content
        return content

    def request(self, url, request_method="GET"):
        """
        Creates request partials to add authentication to any sword related request.
        It also disables redirects to avoid http -> https issues.

        :param url: URL to request
        :param request_method: Request method to use ("GET", "POST", ...)

        :return: Request partial to be used later
        """
        request_map = {
            "GET": requests.get,
            "POST": requests.post,
            "PATCH": requests.patch,
            "PUT": requests.put,
            "DELETE": requests.delete
        }
        method = request_map.get(request_method)
        if not method:
            raise SwordException("Bad method chosen for request")
        return partial(method, url, auth=self.auth_credentials, allow_redirects=False, timeout=self.timeout)
