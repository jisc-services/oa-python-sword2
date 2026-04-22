import pytest

from sword2 import models
from sword2.tests.fixtures import collection, sword_model, deposit_receipt, service_document


class TestBaseModel:

    def test_bad_data(self):
        with pytest.raises(ValueError) as error:
            models.SwordModel({"thisisnot": "gooddata"})
        assert error is not None

    def test_get_dcterms(self, sword_model):
        assert sword_model.get_element("dcterms:abstract") is not None

    def test_get_atom(self, sword_model):
        assert sword_model.get_element("atom:title") is not None

    def test_get_app(self, sword_model):
        assert sword_model.get_element("app:accept") is not None

    def test_get_sword(self, sword_model):
        assert sword_model.get_element("sword:treatment") is not None

    def test_get_many(self, sword_model):
        packaging = sword_model.get_elements_list("sword:acceptPackaging")
        assert packaging is not None
        assert len(packaging) == 2

    def test_singular_set_list(self, sword_model):
        sword_model.set_elements_with_values_list("sword:acceptPackaging", "http://somepackaging.format")
        assert "http://somepackaging.format" in sword_model.get_elements_list("sword:acceptPackaging", True)

    def test_set(self, sword_model):
        sword_model.set_element_with_value("dcterms:abstract", "Different value")
        abstract = sword_model.get_element("dcterms:abstract")
        assert abstract is not None
        assert abstract.text == "Different value"

    def test_set_list(self, sword_model):
        sword_model.set_elements_with_values_list("sword:acceptPackaging", ["fake"])
        packaging = sword_model.get_elements_list("sword:acceptPackaging")
        assert packaging is not None

    def test_merge(self, collection, sword_model):
        collection.title = "Other collection"
        collection.merge(sword_model.xml)
        assert collection.title == "Collection 43"


class TestCollection:

    def test_title(self, collection):
        assert collection.title == "Collection 43"

    def test_packaging(self, collection):
        assert "http://purl.org/net/sword/package/SimpleZip" in collection.packaging
        assert "http://purl.org/net/sword/package/METSDSpaceSIP" in collection.packaging


class TestServiceDocument:

    def test_collections(self, service_document):
        collections = service_document.collections
        assert collections is not None
        assert len(collections) == 1
        assert collections[0].title == "Collection 43"


class TestEntry:

    def test_blank_entry(self):
        entry = models.Entry()
        assert entry.abstract is None
        entry.abstract = "This is now an abstract"
        assert entry.abstract == "This is now an abstract"


class TestDepositReceipt:

    def test_links(self, deposit_receipt):
        links = deposit_receipt.links
        assert links
        assert links[0].href
        assert links[0].rel

    def test_known_iri(self, deposit_receipt):
        edit_iri = deposit_receipt.edit_iri
        assert edit_iri


class TestCreation:

    def test_full_creation(self, service_document):
        new_service_document = models.ServiceDocument()
        new_service_document.version = "2.0"
        new_service_document.max_upload_size = "16777216"
        new_service_document.title = "Main Site"

        new_collection = models.Collection()
        new_collection.link = "http://swordapp.org/col-iri/43"
        new_collection.title = "Collection 43"
        new_collection.set_accept_elements()
        new_collection.abstract = "Collection Description"
        new_collection.packaging = [
            "http://purl.org/net/sword/package/SimpleZip",
            "http://purl.org/net/sword/package/METSDSpaceSIP"
        ]
        new_service_document.collections = [new_collection]

        assert service_document.version == new_service_document.version
        assert service_document.title == new_service_document.title

        collection = service_document.collections[0]
        new_collection = new_service_document.collections[0]
        assert collection.link == new_collection.link
        assert set(collection.packaging) == set(new_collection.packaging)
        assert collection.accept.text == "*/*"
        assert collection.accept_alternate.text == "*/*"

    def test_feed_creation(self, deposit_receipt):
        feed = models.Feed()
        feed.id = "anid"
        assert feed.id == "anid"
        feed.updated = "2017-01-01"
        assert feed.updated == "2017-01-01"
        entry = models.Entry()
        entry.id = "first_id"
        entry.title = "A title"
        second_entry = models.Entry()
        second_entry.id = "second_id"
        second_entry.title = "A second title"
        feed.entries = [entry, second_entry]
        assert {"first_id", "second_id"} == set(entry.id for entry in feed.entries)
