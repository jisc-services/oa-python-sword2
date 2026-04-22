import pytest
from werkzeug.exceptions import HTTPException

from sword2.models import Collection
from sword2.server.util import atom_response, get_container_or_error
from sword2.tests.fixtures import collection, messages, not_implemented_class, repository


class TestUtils:

    def test_not_implemented(self, not_implemented_class):
        with pytest.raises(NotImplementedError) as error:
            not_implemented_class.not_implemented()
        error_string = str(error.value)
        assert "not_implemented" in error_string
        assert "TestRaiseNotImplemented" in error_string

    def test_atom_response(self, collection):
        response_data, status, headers = atom_response(collection)
        assert isinstance(response_data, str)
        new_collection = Collection(response_data)
        assert new_collection.abstract == collection.abstract

    def test_fail_get_container_or_error(self, repository, messages):
        bad_id = "non-existing-id"
        with pytest.raises(HTTPException) as error:
            get_container_or_error(repository, "collection", bad_id)
        response = error.value.response
        assert response.headers.get("Content-Type") == "application/atom+xml; charset=utf-8"
        unicode_data = response.data.decode("utf-8")
        assert messages.ATOM_ERROR.format(bad_id, "collection") in unicode_data

    def test_success_get_container_or_error(self, repository):
        good_id = "correct_container"
        collection = repository.get_collection("collection")
        container = collection.create_container(good_id)
        same_container = get_container_or_error(repository, "collection", good_id)
        assert container.id == same_container.id
