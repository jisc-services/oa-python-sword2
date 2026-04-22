import os
import pytest
import shutil
from functools import partial
from flask import Flask, Response
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED

from sword2.client import SwordClient
from sword2.models import Collection, DepositReceipt, Entry, ServiceDocument, SwordModel
from sword2.server.app import init_app
from sword2.server.util import raise_not_implemented_error_for_method


class XMLFactory:

    RESOURCE_DIR = os.path.join(os.path.realpath(os.path.expanduser(os.path.dirname(__file__))), "resources")

    def __init__(self):
        pass

    @classmethod
    def load_xml(cls, xml_file):
        file = open(os.path.join(cls.RESOURCE_DIR, xml_file))
        data = file.read()
        file.close()
        return data

    @classmethod
    def service_document(cls):
        return ServiceDocument(cls.load_xml("servicedocument.xml"))

    @classmethod
    def collection(cls):
        return Collection(cls.load_xml("collection.xml"))

    @classmethod
    def deposit_receipt(cls):
        return DepositReceipt(cls.load_xml("depositreceipt.xml"))

    @classmethod
    def sword_model(cls):
        return SwordModel(cls.load_xml("collection.xml"))

    @classmethod
    def entry(cls):
        return Entry(cls.load_xml("entry.xml"))


class ZipFactory:

    def __init__(self):
        pass

    @classmethod
    def _create_zip_from_tuples(cls, file_tuples):
        stream = BytesIO()
        with ZipFile(stream, "w") as zip_file:
            for filename, data in file_tuples:
                if filename.endswith("zip"):
                    # Create an embedded zip file
                    zip_file.writestr(filename, cls._create_zip_from_tuples(data).read())
                else:
                    zip_file.writestr(filename, data)
        stream.seek(0)
        return stream

    @classmethod
    def one_file_zip(cls):
        file_tuples = [
            ("file.txt", "This is data.")
        ]
        return cls._create_zip_from_tuples(file_tuples)

    @classmethod
    def zip_with_directories(cls):
        file_tuples = [
            ("file.txt", "This is data."),
            ("directory/important.txt", "This is important data.")
        ]
        return cls._create_zip_from_tuples(file_tuples)

    @classmethod
    def zip_with_directories_same_file_names(cls):
        file_tuples = [
            ("file.txt", "This is data."),
            ("directory/file.txt", "This is data."),
            ("otherdirectory/file.txt", "This is data.")
        ]
        return cls._create_zip_from_tuples(file_tuples)

    @classmethod
    def zip_with_directories_and_embedded_zip(cls):
        file_tuples = [
            ("file.txt", "This is data."),
            ("directory/file.txt", "This is data."),
            ("otherdirectory/file.txt", "This is data."),
            ("directory/withembedded.zip", [
                ("zfile.txt", "Zipped data 1."),
                ("zdir/zfile.txt", "Zipped data 2."),
            ]),
            ("withembedded.zip", [
                ("zfile.txt", "Zipped data 1."),
                ("zdir/zfile.txt", "Zipped data 2."),
            ])
        ]
        return cls._create_zip_from_tuples(file_tuples)


@pytest.fixture
def service_document():
    return XMLFactory.service_document()


@pytest.fixture
def deposit_receipt():
    return XMLFactory.deposit_receipt()


@pytest.fixture
def collection():
    return XMLFactory.collection()


@pytest.fixture
def entry():
    return XMLFactory.entry()


@pytest.fixture
def sword_model():
    return XMLFactory.sword_model()


class SwordTestClient(SwordClient):

    def __init__(self, request_impl, base_collection_iri, auth_credentials={}, service_document_iri=None):
        self.request_impl = request_impl
        super().__init__(base_collection_iri, auth_credentials, service_document_iri=service_document_iri)

    def request(self, url, request_method=None):
        """
        Creates request partials to add authentication to any sword related request
        It also disables redirects to avoid http -> https issues.

        :param url: URL to request
        :param request_method: Request method to use ("GET", "POST"..))

        :return: Request partial to be used later
        """
        request_map = {
            "GET": self.request_impl.get,
            "POST": self.request_impl.post,
            "PATCH": self.request_impl.patch,
            "PUT": self.request_impl.put,
            "DELETE": self.request_impl.delete
        }
        return partial(request_map.get(request_method, self.request_impl.get), url)


@pytest.fixture
def sword_client(test_client_no_auth):
    return SwordTestClient(
        test_client_no_auth,
        "http://localhost/collections",
        service_document_iri="http://localhost/"
    )


@pytest.fixture
def zip_file():
    return ZipFactory.one_file_zip()


@pytest.fixture
def zip_file_with_directories():
    return ZipFactory.zip_with_directories()


@pytest.fixture
def zip_file_with_directories_same_file_names():
    return ZipFactory.zip_with_directories_same_file_names()

@pytest.fixture
def zip_file_with_embedded_zip():
    return ZipFactory.zip_with_directories_and_embedded_zip()


# All this does is add a 'content' method to mimic a requests response.
class TestResponse(Response):

    @property
    def content(self):
        return self.data


# Simple test class to test raise_not_implemented_error_for_method
class TestRaiseNotImplemented:

    raise_not_implemented_error = raise_not_implemented_error_for_method

    def not_implemented(self):
        self.raise_not_implemented_error("not_implemented")

    def implemented(self):
        return None


def create_app():
    app = Flask(__name__)

    app.config["REPO_ARGUMENTS"] = ["/tmp/sword-test"]
    app.config["SERVER_NAME"] = "localhost"
    app.config["TESTING"] = True
    app.config["DEBUG"] = True
    app.config["USERS"] = {
        "admin": "admin"
    }
    app.config["ZIP_COMPRESSION"] = ZIP_DEFLATED
    app.config["ZIP_STD_COMPRESS_LEVEL"] = None

    app.response_class = TestResponse

    return app


app = create_app()
init_app(app)


@pytest.fixture
def test_client():
    app = create_app()
    app.config["AUTH_IMPL"] = "sword2.server.auth.SwordBasicAuthentication"
    init_app(app)
    return app.test_client()


@pytest.fixture
def test_client_no_auth():
    app = create_app()
    init_app(app)
    return app.test_client()


@pytest.fixture
def repository():
    from sword2.server.views.blueprint import repository
    with app.app_context():
        repository.create_collection("collection")
        yield repository
    shutil.rmtree("/tmp/sword-test", ignore_errors=True)


@pytest.fixture
def messages():
    from sword2.server.globals import messages
    with app.app_context():
        yield messages


@pytest.fixture
def not_implemented_class():
    return TestRaiseNotImplemented()
