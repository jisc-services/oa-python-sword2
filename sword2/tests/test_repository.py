import pytest
from io import BytesIO
from zipfile import ZipFile

from sword2.tests.fixtures import entry, zip_file, zip_file_with_directories, zip_file_with_directories_same_file_names, zip_file_with_embedded_zip, app
from sword2.server.repository import FileRepository


@pytest.fixture
def repo():
    repo = FileRepository("/tmp/sword-tests")
    repo._clean_dir()
    yield repo
    repo._clean_dir()


class TestRepository():

    def test_create_collection(self, repo):
        collection = repo.create_collection("collection")
        assert repo.collection_exists(collection.atom_title)
        assert repo.collections

    def test_create_metadata_entry(self, repo, entry):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry, "entry")
            assert repo_container
            assert repo_container.id == "entry"
            assert not repo_container.contents

    def test_load_a_created_metadata_entry(self, repo, entry):
        with app.app_context():
            # Create entry (persist as file)
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry, "entry")
            assert repo_container
            # Load entry (from file)
            loaded = repo_collection.get_container("entry")
            assert loaded
            assert loaded.id == "entry"

    def test_feed(self, repo, entry):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry, "entry")
            assert repo_container
            with app.app_context():
                feed = repo_collection.to_feed()
            assert repo_container.updated == feed.updated

    def test_binary_deposit(self, repo, entry):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry)
            assert repo_container
            txt_file = BytesIO(b'I am a text file')
            repo_container.add_or_replace_binary_file(txt_file, "file.txt")
            assert repo_container.contents
            assert repo_container.contents == ["file.txt"]

    def test_zip_deposit(self, repo, entry, zip_file):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry)
            assert repo_container
            repo_container.add_or_replace_binary_file(zip_file, "myzip.zip")

            assert {"myzip.zip", "file.txt"} == set(repo_container.contents)
            request_contents = repo_container.current_request_contents
            assert ("myzip.zip", False) in request_contents
            assert ("file.txt", True) in request_contents

    def test_zip_with_directory(self, repo, entry, zip_file_with_directories):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry)
            assert repo_container
            repo_container.add_or_replace_binary_file(zip_file_with_directories, "withdirectories.zip")
            assert {"withdirectories.zip", "file.txt", "important.txt"} == set(repo_container.contents)

    def test_zip_with_same_file_names(self, repo, entry, zip_file_with_directories_same_file_names):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry)
            assert repo_container
            repo_container.add_or_replace_binary_file(zip_file_with_directories_same_file_names, "samefiles.zip")
            assert {"samefiles.zip", "file.txt", "_file.txt", "__file.txt"} == set(repo_container.contents)

    def test_zip_all_files(self, repo, entry, zip_file):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry)
            assert repo_container
            repo_container.add_or_replace_binary_file(zip_file, "myzip.zip")
            data = repo_container.get_all_file_content_as_zip()
            with ZipFile(data) as zip_file:
                info_list = list(zip_file.infolist())
                assert info_list
                text_file = info_list[0]
                assert text_file.filename == "file.txt"
                assert zip_file.read(text_file) == b"This is data."

    def test_zip_with_embedded_zip(self, repo, entry, zip_file_with_embedded_zip):
        with app.app_context():
            repo_collection = repo.create_collection("collection")
            repo_container = repo_collection.deposit_metadata(entry)
            assert repo_container
            repo_container.add_or_replace_binary_file(zip_file_with_embedded_zip, "~withembedded.zip")
            assert {"withembedded.zip", "file.txt", "_file.txt", "__file.txt", "~withembedded.zip", "~~withembedded.zip"} == set(repo_container.contents)

