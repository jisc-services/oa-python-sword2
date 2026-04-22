from base64 import b64encode
from functools import partial
from flask import url_for
from io import BytesIO
from zipfile import ZipFile

from sword2.models import DepositReceipt, Entry, ErrorDocument, Feed
from sword2.tests.fixtures import app, entry, messages, repository, test_client


class TestServer:

    @staticmethod
    def url_for(*args, **kwargs):
        with app.app_context():
            return url_for(*args, **kwargs)

    def request_with_auth_partial(self, client):
        return partial(self.request_with_auth, client)

    @staticmethod
    def request_with_auth(client, url, method, *args, **kwargs):
        b64_str = b64encode(b"admin:admin").decode("ascii")
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Basic {b64_str}"
        return client.open(url, method=method, headers=headers, *args, **kwargs)

    def test_service_doc(self, test_client):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.service_document"),
            "GET"
        )
        assert response.data
        assert response.status_code == 200

    def test_bad_auth(self, test_client, repository, entry, messages):
        response = test_client.post(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            data=str(entry)
        )
        assert response.status_code == 401
        assert response.data
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.NOT_AUTHED_ERROR

    def test_post_and_get_collection(self, test_client, repository, entry):
        authed_client = self.request_with_auth_partial(test_client)
        # POST metadata (entry)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry)
        )
        receipt = DepositReceipt(response.data.decode("utf-8"))
        assert receipt.em_iri
        assert receipt.em_iri == self.url_for(
            "sword2-server.em_iri", collection_id="collection", container_id=receipt.id)

        # POST a binary file as an attachment
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data={"attachment": (BytesIO(b'this is text'), 'test.txt')}
        )
        receipt = DepositReceipt(response.data.decode("utf-8"))
        link_hrefs = [link.href for link in receipt.links]
        assert link_hrefs
        link = self.url_for(
            "sword2-server.em_iri", collection_id="collection", container_id=receipt.id, resource_name="test.txt")
        assert link in link_hrefs

        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "GET"
        )
        feed = Feed(response.data.decode("utf-8"))
        assert feed.id == self.url_for("sword2-server.collection_iri", collection_id="collection")
        assert feed.title == "Collection: 'collection'"
        assert len(feed.entries) == 2

    def test_post_collection_multipart(self, test_client, repository, entry):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data={
                "atom": (BytesIO(str(entry).encode("utf-8")), "metadata.xml"),
                "payload": (BytesIO(b'this is text'), 'test.txt')
            }
        )
        assert response.status_code == 201
        DepositReceipt(response.data)

    def test_bad_post(self, test_client, repository, entry, messages):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=''
        )
        assert response.status_code == 400
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.DATA_WAS_NOT_XML_ERROR

        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data={
                "file": (BytesIO(b'wrong attachment'), 'text.txt')
            }
        )
        assert response.status_code == 400
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.NO_FILE_ERROR

        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            headers={
                "Content-Type": "text/plain",
                "Content-Disposition": "attachment; filename="
            },
            data="Some data"
        )
        assert response.status_code == 400
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.NO_FILE_ERROR

        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data={
                "atom": (BytesIO(str(entry).encode("utf-8")), "metadata.xml")
            }
        )
        assert response.status_code == 400
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.BAD_MULTIPART_ERROR

    def test_edit_iris(self, test_client, repository, entry, messages):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry),
            headers={"In-Progress": "true"}
        )
        receipt = DepositReceipt(response.data)
        assert receipt.edit_iri
        iri = receipt.edit_iri

        entry.atom_title = "This now has a different title."

        response = authed_client(iri, "PUT", data=str(entry), headers={"In-Progress": "true"})
        assert response.status_code == 204

        response = authed_client(iri, "GET")
        new_entry = Entry(response.data)
        assert new_entry.atom_title == "This now has a different title."

        response = authed_client(
            iri,
            "POST",
            data='',
            headers={"In-Progress": "false"}
        )
        assert response.status_code == 200
        receipt = DepositReceipt(response.data)
        assert receipt.verbose_description == messages.DEPOSIT_COMPLETE

    def test_edit_iris_multipart(self, test_client, repository, entry, messages):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry),
            headers={"In-Progress": "true"}
        )
        receipt = DepositReceipt(response.data)
        assert receipt.edit_iri
        iri = receipt.edit_iri

        entry.atom_title = "This now has a different title."

        response = authed_client(
            iri,
            "POST",
            data={
                "atom": (BytesIO(str(entry).encode("utf-8")), "metadata.xml"),
                "payload": (BytesIO(b'this is text'), 'test.txt')
            },
            headers={"In-Progress": "true"}
        )
        assert response.status_code == 201
        receipt = DepositReceipt(response.data)
        assert receipt.atom_title == "This now has a different title."

        response = authed_client(
            iri,
            "PUT",
            data={
                "atom": (BytesIO(str(entry).encode("utf-8")), "metadata.xml"),
                "payload": (BytesIO(b'this is text'), 'test.txt')
            }
        )
        assert response.status_code == 204
        assert not response.data

    def test_delete_edit_iri(self, test_client, repository, entry):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry),
            headers={"In-Progress": "true"}
        )
        receipt = DepositReceipt(response.data)
        iri = receipt.edit_iri

        response = authed_client(
            iri,
            "DELETE"
        )
        assert response.status_code == 204

        response = authed_client(
            iri,
            "GET"
        )
        assert response.status_code == 404

    def test_fail_edit_iris(self, test_client, repository, entry, messages):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry),
            headers={"In-Progress": "true"}
        )
        receipt = DepositReceipt(response.data)
        iri = receipt.edit_iri

        response = authed_client(iri, "PUT", data='')
        assert response.status_code == 400
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.DATA_WAS_NOT_XML_ERROR

    def test_edit_media_iris(self, test_client, repository, entry):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry),
            headers={"In-Progress": "true"}
        )
        receipt = DepositReceipt(response.data.decode("utf-8"))
        assert receipt.em_iri
        iri = receipt.em_iri

        response = authed_client(
            f"{iri}/test.txt",
            "PUT",
            data={
                "attachment": (BytesIO(b'this is text'), 'test.txt')
            },
            headers={"In-Progress": "true"}
        )
        assert response.status_code == 204

        response = authed_client(f"{iri}/test.txt", "GET")
        assert response.status_code == 200
        assert response.data == b'this is text'

        response = authed_client(
            iri,
            "POST",
            data={
                "attachment": (BytesIO(b'this is other text'), 'othertest.txt')
            },
            headers={"In-Progress": "true"}
        )
        assert response.status_code == 201

        response = authed_client(f"{iri}/othertest.txt", "GET")
        assert response.status_code == 200
        assert response.data == b'this is other text'

        response = authed_client(iri, "GET")
        assert response.status_code == 200
        assert response.data

        with ZipFile(BytesIO(response.data)) as zip_file:
            info_list = list(zip_file.infolist())
            assert len(info_list) == 2
            assert set(zip_info.filename for zip_info in info_list) == {"othertest.txt", "test.txt"}
            # Cannot do a list comprehension as zip_file will be out of scope
            text_content_set = set()
            for zip_info in info_list:
                text_content_set.add(zip_file.read(zip_info))
            assert text_content_set == {b"this is other text", b"this is text"}

    def test_delete_edit_media_iri(self, test_client, repository, entry, messages):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry),
            headers={"In-Progress": "true"}
        )
        receipt = DepositReceipt(response.data.decode("utf-8"))
        iri = receipt.em_iri

        response = authed_client(
            f"{iri}/test.txt",
            "PUT",
            data={
                "attachment": (BytesIO(b'this is text'), 'test.txt')
            },
            headers={"In-Progress": "true"}
        )
        assert response.status_code == 204

        response = authed_client(
            f"{iri}/bad.txt",
            "GET"
        )
        assert response.status_code == 404
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.DID_NOT_FIND_FILE_ERROR.format("bad.txt")

        response = authed_client(
            f"{iri}/test.txt",
            "DELETE"
        )
        assert response.status_code == 204

        response = authed_client(
            f"{iri}/test.txt",
            "GET"
        )
        assert response.status_code == 404

    def test_fail_edit_media_iris(self, test_client, repository, entry, messages):
        authed_client = self.request_with_auth_partial(test_client)
        response = authed_client(
            self.url_for("sword2-server.collection_iri", collection_id="collection"),
            "POST",
            data=str(entry),
            headers={"In-Progress": "true"}
        )
        receipt = DepositReceipt(response.data.decode("utf-8"))
        iri = receipt.em_iri

        response = authed_client(
            f"{iri}/test.txt",
            "PUT",
            data={
                "file": (BytesIO(b'wrong file key'), 'test.txt')
            },
            headers={"In-Progress": "true"}
        )
        assert response.status_code == 400
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.NO_FILE_ERROR

        response = authed_client(
            iri,
            "POST",
            data={
                "file": (BytesIO(b'wrong file key'), 'test.txt')
            },
            headers={"In-Progress": "true"}
        )
        assert response.status_code == 400
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.NO_FILE_ERROR

        response = authed_client(f"{iri}/test.txt", "GET")
        assert response.status_code == 404
        receipt = ErrorDocument(response.data)
        assert receipt.summary == messages.DID_NOT_FIND_FILE_ERROR.format("test.txt")
