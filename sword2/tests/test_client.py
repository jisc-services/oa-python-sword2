"""
Tests for the SwordClient.
"""
from io import BytesIO
from unittest.mock import patch, Mock
from zipfile import ZipFile

import pytest
from requests.exceptions import ReadTimeout

import sword2
from sword2.client import SwordClient
from sword2.client.util import SwordException
from sword2.tests.fixtures import entry, repository, sword_client, test_client_no_auth


class MockResponse:
    """
    Mock responses to return from patched calls to requests.get / post etc. when mocking the
    requests library used by the SwordClient.
    """
    def __init__(self, location, status_code, method='GET', content=None):
        # Note that the value of the 'Location' header URL doesn't matter for the purposes of
        # these tests, it just has to exist.
        self.headers = {'Location': location}
        # Set a status_code, which will determine how the response is dealt with by SwordClient.
        self.status_code = status_code
        # An internal request object with a 'method' attribute is also required as it is read by
        # SwordClient when it handles HTTP redirects.
        self.request = Mock()
        self.request.method = method
        # Set the content string, which SwordClient will attempt to parse as XML, if the test is
        # intended to reach that point of the code.
        self.content = content


class TestSwordClient():
    # ====================
    # Implementation notes
    # ====================
    #
    # Previously, some of these tests made real HTTP requests to a third-party testing server that
    # is not under Jisc's control, and has since proved to be unreliable. These tests have been
    # reworked to use the @patch decorator to mock the 'requests' library that SwordClient uses
    # to make HTTP requests.
    #
    # This mock object is passed as a parameter to each of these tests, will lets each one
    # manipulate its behaviour. This allows us to test SwordClient without performing any real HTTP
    # requests: Instead, we simulate the desired behaviour for each request that SwordClient
    # performs. More information is provided in each test case below.
    #
    # See https://docs.python.org/3/library/unittest.mock.html#unittest.mock.patch for more
    # information on @patch.
    #
    # TODO: Some of the tests here predate the use of @patch and use the fixtures.SwordTestClient
    #   instead. The SwordTestClient approach is a bit clunky, being a subclass of SwordClient
    #   with an overridden 'request' method which must always be kept functionally equivalent to
    #   the real 'request' method on SwordClient. These should be rewritten to use the @patch
    #   approach in the future, where feasible.

    def test_service_doc(self, sword_client, repository):
        service_doc = sword_client.get_service_document()

        assert service_doc is not None

    def test_metadata_deposits(self, sword_client, repository, entry):
        receipt = sword_client.metadata_deposit(entry, in_progress=True, collection_id="collection")

        assert receipt is not None
        assert not receipt.is_error()
        assert receipt.location
        assert receipt.location == receipt.edit_iri

        entry.atom_title = "A new title."

        no_content = sword_client.replace_metadata(entry, in_progress=True, deposit_receipt=receipt)

        assert no_content is None

        receipt = sword_client.add_metadata(entry, in_progress=True, deposit_receipt=receipt)

        assert receipt
        assert receipt.atom_title == "A new title."

        receipt = sword_client.get_deposit_receipt_with_metadata(deposit_receipt=receipt)

        assert receipt
        assert receipt.atom_title == "A new title."

    def test_file_deposits(self, sword_client, repository):
        receipt = sword_client.file_deposit(
            "nice.txt",
            BytesIO(b'this is text'),
            in_progress=True,
            collection_id="collection"
        )

        assert receipt is not None
        assert not receipt.is_error()
        assert receipt.location
        assert receipt.location == receipt.edit_iri

        content = sword_client.get_file("nice.txt", deposit_receipt=receipt)

        assert content == b'this is text'

        sword_client.add_file(
            "other_file.txt",
            BytesIO(b'this is other text'),
            in_progress=True,
            deposit_receipt=receipt
        )

        content = sword_client.get_file("other_file.txt", deposit_receipt=receipt)

        assert content == b'this is other text'

        sword_client.replace_file(
            "nice.txt",
            BytesIO(b'this is new text'),
            in_progress=True,
            deposit_receipt=receipt
        )

        content = sword_client.get_file("nice.txt", deposit_receipt=receipt)

        assert content == b'this is new text'

        zip_content = sword_client.get_content(deposit_receipt=receipt)
        assert zip_content

        with ZipFile(BytesIO(zip_content)) as zip_file:
            assert {"other_file.txt", "nice.txt"} == set(zip_info.filename for zip_info in zip_file.infolist())

        assert sword_client.delete_file("nice.txt", deposit_receipt=receipt)
        assert sword_client.delete_all_content(deposit_receipt=receipt)

    def test_multipart_deposits(self, sword_client, repository, entry):
        receipt = sword_client.multipart_deposit(
            entry,
            "nice.txt",
            BytesIO(b'this is text'),
            in_progress=True,
            collection_id="collection"
        )

        assert receipt is not None
        assert not receipt.is_error()

        content = sword_client.get_file("nice.txt", deposit_receipt=receipt)

        assert content == b'this is text'

        entry.atom_title = "A new title."

        data = sword_client.replace_multipart_deposit(
            entry,
            "nice.txt",
            BytesIO(b'this is new text.'),
            in_progress=True,
            deposit_receipt=receipt
        )

        assert not data

        content = sword_client.get_file("nice.txt", deposit_receipt=receipt)

        assert content == b'this is new text.'

        receipt = sword_client.add_multipart_deposit(
            entry,
            "nice.txt",
            BytesIO(b'this is newer text.'),
            in_progress=True,
            deposit_receipt=receipt
        )

        assert receipt is not None
        assert not receipt.is_error()

        assert receipt.atom_title == "A new title."

        content = sword_client.get_file("nice.txt", deposit_receipt=receipt)

        assert content == b'this is newer text.'

    def test_bad_zip(self, sword_client, repository, entry):
        receipt = sword_client.multipart_deposit(
            entry,
            "nice.zip",
            BytesIO(b'this is text'),
            in_progress=True,
            collection_id="collection"
        )

        assert receipt is not None
        assert receipt.is_error()

    def test_delete_not_found(self, sword_client, repository, entry):
        receipt = sword_client.metadata_deposit(
            entry,
            in_progress=True,
            collection_id="collection"
        )

        assert receipt is not None
        assert not receipt.is_error()

        success = sword_client.delete_file("not_a_file.txt", deposit_receipt=receipt)
        assert not success

    @patch('sword2.client.client.requests')
    def test_response_errors(self, requests_mock):
        """
        Test that:
        1. When an HTTP 400 status code is returned, an ErrorDocument is returned
        2. When an HTTP 200 status code is returned, but the response content cannot be parsed as
           XML, a SwordException is raised.
        """
        # Mock setup
        # ==========
        # We replace the requests.get() function with a mock that returns a MockResponse each
        # time it is called.
        requests_mock.get.side_effect = [
            # The first response returned is configured with a status code of 400, for which we
            # expect an ErrorDocument to be returned.
            MockResponse("http://foo-bar.com", 400),
            # The second response returned is configured with a status code of 200, but has
            # content that is not valid XML, which is expected to cause a SwordException when it
            # can't be parsed.
            MockResponse("http://foo.com", 200, content="NOT XML"),
        ]

        # Initialize the client.
        client = SwordClient("foo-bar.com")

        # Test [1]

        # client.request() is called, returning a partial function containing a call to the mocked
        # requests.get() function.
        error_req = client.request("http://foo-bar.com", "GET")

        # When the partial function is passed to client._send_data, _send_data calls it and the
        # first MockResponse defined above is returned, which is found to not have a 2xx,
        # status_code, which causes an ErrorDocument to be returned.
        error_doc = client._send_data(error_req, {})

        # Check an ErrorDocument was returned.
        assert isinstance(error_doc, sword2.models.ErrorDocument)
        assert error_doc.is_error()

        # Test [2]

        # As before, client.request returns a partial function.
        error_not_xml_req = client.request("http://foo.com", "GET")

        with pytest.raises(SwordException) as se:
            # _send_data calls the partial function and this time the MockResponse's status_code
            # is OK. client._send_data proceeds to parse the response's .content as XML, which
            # fails, causing a SwordException to be raised.
            client._send_data(error_not_xml_req, {})

        # Check the error message.
        assert str(se.value) == "ERROR: the server returned malformed xml or a webpage."

    @patch('sword2.client.client.requests')
    def test_ten_http_redirects(self, requests_mock):
        """
        Test that ten http redirects are followed by the SwordClient and do not cause an
        exception to be raised.
        """
        # Mock Setup
        # ===========
        # Create 10 redirects for requests.get to return, followed by one status 200 response.
        requests_mock.get.side_effect = [
            MockResponse("http://foo-bar.com", 301),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 303),
            MockResponse("http://foo-bar.com", 303),
            MockResponse("http://foo-bar.com", 303),
            MockResponse("http://foo-bar.com", 301),
            MockResponse("http://foo-bar.com", 301),
            MockResponse("http://foo-bar.com", 301),
            MockResponse("http://foo-bar.com", 301),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 200),
        ]

        # Initialize the SwordClient.
        client = SwordClient("http://foo-bar.com")

        # Call client.request() to obtain the partial function.
        few_redirects = client.request("http://foo-bar.com", "GET")

        # Pass the partial function into client._get_response.
        response = client._get_response(few_redirects)

        # Check that the SwordClient followed all 10 redirects and reached the final MockResponse.
        assert response.status_code == 200

    @patch('sword2.client.client.requests')
    def test_too_many_http_redirects(self, requests_mock):
        """
        Test that a SwordException is raised when more than ten redirects are encountered in a GET
        request.
        """
        # Mock Setup
        # ===========
        # Create 11 mock redirect MockResponses for requests.get to return, followed by one that
        # resolves with status code 200, which should never be reached.
        requests_mock.get.side_effect = [
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 301),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 307),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 302),
            MockResponse("http://foo-bar.com", 200),
        ]
        # Instantiate the SwordClient
        client = SwordClient("http://foo-bar.com")

        # Call client.request() to obtain the partial function.
        too_many_redirects = client.request("http://foo-bar.com", "GET")

        with pytest.raises(SwordException) as se:
            # Check that a SwordException is raised when the SwordClient follows more than 10
            # redirects.
            client._get_response(too_many_redirects)

        # Check the error message is as expected.
        assert str(se.value) == "ERROR: Request has a redirect loop"

    @patch('sword2.client.client.requests')
    def test_timeout(self, requests_mock):
        """
        Test that a SwordException is raised when a read-timeout occurs when making a GET request.
        """
        # Mock Setup
        # ===========
        # Define a function that immediately raises a ReadTimeout exception. The
        # SwordClient._get_response method explicitly catches this exception via its
        # error_on_timeout decorator.
        def read_timeout(*args, **kwargs):
            raise ReadTimeout()

        # Attach the function to the mock, so when it is called later, the ReadTimeout exception
        # is raised.
        requests_mock.get = read_timeout

        # Instantiate the SwordClient. This uses the default timeout specified in SwordClient - the
        # value doesn't matter because all we are testing here is that, when a ReadTimeout
        # exception occurs, SwordClient handles it and raises a SwordException instead.
        client = SwordClient("foo-bar.com")

        # Get the partial function containing the mock request.get function.
        should_timeout = client.request("http://foo-bar.com", "GET")

        with pytest.raises(SwordException) as se:
            # Pass the partial to _get_response. When it's called, the ReadTimeout will be raised,
            # which will be caught and a SwordException raised instead.
            client._get_response(should_timeout)

        # Check the message in the SwordException is as expected.
        assert str(se.value) == "ERROR: Request timed out after 120 seconds."
