"""
Repository model classes

These are used to configure the SWORD2 server to work with any implementation of a repository.

IMPORTANT NOTE re. Handling of submitted Zip files:
    The default implementation UNPACKS received Zip files flattening them (i.e. removing nested directory structure).
    Any non-zip files within a zipped hierarchical structure that have identical filenames are renamed by
    (successively) prepending "_" to the original filename to avoid overwriting files during the flattening process.
    Any zip files within the submitted zip file (i.e. nested zip files) are renamed by prepending them with "~" so that
    unpacked zipfiles can be differentiated from the original zip file, these nested zip files are NOT unpacked.
The Repo* classes are abstract classes that should be implemented by a developer, the File* classes are an
implementation of a file-system based repository.
"""
import glob
import os
import shutil
from io import BytesIO
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, ZIP_STORED, ZIP_DEFLATED

from flask import current_app

from sword2.models import Collection, Entry, Feed
from sword2.server.exceptions import RepositoryError
# from sword2.server.globals import messages
from sword2.server.util import now_to_date_string, raise_not_implemented_error_for_method


class RepoContainer(Entry):
    """
    A RepoContainer is a deposit container. This has all the methods required
    to add, replace and delete content of a deposit.
    """
    DERIVED_RESOURCE = "http://purl.org/sword/terms/derivedResource"
    ORIGINAL_RESOURCE = "http://purl.org/net/sword/terms/originalDeposit"
    rel_value_dict = {
        True: DERIVED_RESOURCE,
        False: ORIGINAL_RESOURCE
    }
    # Add the raise_not_implemented error function to this class.
    raise_not_implemented_error = raise_not_implemented_error_for_method


    def __init__(self, data, id):
        """
        Defines a default for in progress and adds an id for this deposit.

        :param data: Some kind of Entry data (binary, string, other Entries)
        :param id: Id to give this container
        """
        super().__init__(data)
        self.id = id
        self.current_request_contents = []
        self.metadata_is_stored = False
        _config = current_app.config
        self.compression = _config.get('ZIP_COMPRESSION', ZIP_DEFLATED)
        self.compress_level = _config.get('ZIP_STD_COMPRESS_LEVEL')  # None --> default compression

    def _load_metadata(self, entry_data):
        """
        replace the metadata in this instance but keep the ID.

        :param entry_data: Some kind of entry data (binary, string, other Entries)
        """
        _id = self.id
        super().__init__(entry_data)
        self.id = _id

    def update_metadata(self, entry_data):
        """
        Merge the new data with our current metadata. Will keep the ID of the current container.

        :param entry_data: Some kind of entry data (binary, string, other Entries)
        """
        self.metadata_is_stored = True
        _id = self.id
        # Cast to an Entry then collect the etree instance from the class instance
        # This allows more types of entry_data for this function.
        self.merge(Entry(entry_data).xml)
        self.id = _id
        self._set_updated_and_store_metadata()

    def add_or_replace_metadata(self, entry_data):
        """
        Load new metadata and then store the metadata in the container.

        :param entry_data: Some kind of entry data (binary, string, other Entries)
        """
        self.metadata_is_stored = True
        self._load_metadata(entry_data)
        self._set_updated_and_store_metadata()

    def _set_last_updated(self):
        """
        Set the atom:updated value of this metadata to an ISO8601 formatted datetime string of the time right now.
        """
        self.updated = now_to_date_string()

    def _set_updated_and_store_metadata(self):
        """
        For functions that don't use _store_metadata after setting the last_updated value,
        this helper function will run _store_metadata after setting last_updated.
        """
        self._set_last_updated()
        self._store_metadata()

    def _store_metadata(self):
        """
        Will store metadata to make sure it persists between requests, and make sure the ID stays the same.

        :return: No return value
        """
        self.raise_not_implemented_error("_store_metadata")

    def _non_orig_zip_content_generator(self):
        """
        Create a generator of each non original zip file that yields the filename of the file, and the stream of the file.

        yield: Tuple of filename and a filestream of the file corresponding to the filename.
        """
        for filename in self.contents:
            # Return all files that are NOT original zip filex
            if not (filename.endswith(".zip") and not filename.startswith("~")):
                yield filename, self.get_file_content(filename)

    def get_all_file_content_as_zip(self):
        """
        Get all file content in this container that is not a zip file, zip up this content and return the stream
        of the zip.

        This is used when no filename is given for a GET request against the EM-IRI.

        :return: File stream of the zipped content
        """
        zip_stream = BytesIO()
        with ZipFile(zip_stream, "w", compression=self.compression, compresslevel=self.compress_level) as zip_file:
            for filename, file_stream in self._non_orig_zip_content_generator():
                zip_file.writestr(filename, file_stream.read())

        zip_stream.seek(0)
        return zip_stream

    @classmethod
    def _get_files_from_zip_file_with_flattened_names(cls, zip_file):
        """
        Iterate over the files in a zip file, then yield the basename of the file path and the zip_info of each file.

        This will also make sure there are no duplicate filenames.

        :param zip_file: zipfile.ZipFile instance

        :yield: basename of path to file inside zip file, and zipfile.ZipInfo of that file as a tuple.
        """
        all_file_names = set()
        for zip_info in zip_file.infolist():
            filename = zip_info.filename
            # Ignore directories
            if filename.endswith("/"):
                continue

            filename = os.path.basename(filename)
            # If an embedded zip file, we rename it with a '~' prefix
            if filename.endswith(".zip"):
                filename = f"~{filename}"
                prefix = "~"
            else:
                prefix = "_"
            # Avoid overwriting files with the same name, by prepending it with (successive) '_' chars
            while filename in all_file_names:
                filename = f"{prefix}{filename}"

            all_file_names.add(filename)

            yield filename, zip_info

    def _unzip_file_and_store_resources(self, stream):
        """
        If we are adding a zip file, unzip the file, and add all the other files separately

        This will unzip the files as a flat structure - any directories will be removed and all files
        will be at the top level of the container.

        This will raise a RepositoryError if the stream is not actually a zip file.

        :param stream: Zip file stream
        """
        try:
            with ZipFile(stream) as zip_file:
                # For each file in the zip file, get a flattened name (name without any path)
                # and the zip_info object which we can then use to open the file and store it.
                for filename, zip_info in self._get_files_from_zip_file_with_flattened_names(zip_file):
                    with zip_file.open(zip_info) as file_in_zip:
                        self.add_or_replace_binary_file(file_in_zip, filename, True)
        except BadZipFile:
            # If the stream is not a zip file, error out as this is obviously not intended.
            raise RepositoryError("Repository received a zip file that was not a zip file", status_code=400)

    def _add_file_to_current_request_contents(self, filename, is_derived):
        """
        For each deposit request, we must store which files we received were originally sent
        and which ones were derived from a resource (AKA unzipped from a zip file.)

        This will then be used in the view to return the atom:link objects for each resource made in this request.

        :param filename: Filename of file
        :param is_derived: Whether this file is a derivedResource from a zip file
        """
        self.current_request_contents.append((filename, is_derived))

    def add_or_replace_binary_file(self, stream, filename, is_derived=False):
        """
        Method for adding or replacing binary data.

        :param stream: Some sort of file stream
        :param filename: Filename for this stream
        :param is_derived: Boolean - whether file is derived from a zip file

        :return: No return value
        """
        # We only unpack "top-level" zip files (i.e. not zipfiles that are embedded within other zipfiles)
        if filename.endswith(".zip") and not is_derived:
            # Remove any leading '~' which is used to indicate a derived zipfile
            while filename[0] == "~":
                filename = filename[1:]
            self._add_file_to_current_request_contents(filename, is_derived)
            self._unzip_file_and_store_resources(stream)
            stream.seek(0)  # Reposition zip stream file ptr to start, so that the next statement saves entire zip file
        else:
            self._add_file_to_current_request_contents(filename, is_derived)
        self._store_binary_file(stream, filename, is_derived)
        self.add_part(filename, allow_duplicates=False)
        if not is_derived:
            self._set_updated_and_store_metadata()

    def _store_binary_file(self, stream, filename, is_derived):
        """
        Will store the binary file in the container.

        :param stream: File stream
        :param filename: Filename for this file
        :param is_derived: Whether this file is derived from a ZIP file or not.

        With the case of is_derived, this likely doesn't need to be used when storing the file. However,
        if an implementation did want to store the information of whether the file was derived, they could
        by using the parameter.

        :return: No return value
        """
        self.raise_not_implemented_error("_store_binary_file")

    def get_file_content(self, filename):
        """
        Get content for a given file.

        :param filename: Filename to get content for

        :return: File stream of content
        """
        self.raise_not_implemented_error("get_file_content")

    @property
    def contents(self):
        """
        List of all file content in this container.

        :return: List of contents in the container
        """
        self.raise_not_implemented_error("contents")

    @property
    def in_progress(self):
        """
        In an implementation, this should begin as True and then be set to False using the setter.

        So, if this was stored in a database, you would collect the in_progress value from the database, and
        set it to False in the implementation of the _process_completed_deposit method.

        :return: Boolean of whether we're in progress or not
        """
        # Does not persist, so always run complete_deposit if in_progress = False in the request.
        return True

    @in_progress.setter
    def in_progress(self, value):
        """
        Setter for in_progress.

        Will only ever be used once in complete_deposit.

        :param value: True/False value to set in_progress to.
        """
        pass

    def complete_deposit(self):
        """
        Finish the deposit and process all files in the container.

        This will be executed if a request has not set the In-Progress header, or set the header to false.
        """
        if self.in_progress:
            self.in_progress = False
            self._process_completed_deposit()

    def _process_completed_deposit(self):
        """
        Process the deposit after deposit completion.

        This is up to the implementation to decide on what this does.
        """
        pass

    def delete(self):
        """
        Method to delete the container.

        :return: whether the container was successfully deleted
        """
        self.raise_not_implemented_error("delete")

    def delete_content(self, filename=None):
        """
        public method to delete file content.

        Wraps the _set_updated_and_store_metadata method to delete content, so it will update last_updated if content
        has been deleted.

        If filename is None, _delete_content should delete ALL the file content.

        :param filename: Filename to delete

        :return: whether the file was successfully deleted
        """
        successful = self._delete_content(filename)
        if successful:
            self.remove_parts(filename)
            self._set_updated_and_store_metadata()
        return successful

    def _delete_content(self, filename):
        """
        private method to delete file content.

        If the filename is not None, it will attempt to delete the file with the specified filename.
        If the filename is None, it will delete all file content from the container.

        This should be implemented by a user of this library.

        :param filename: Filename to delete, or None. Has no default as it's a private method.

        :return: whether the file was successfully deleted
        """
        self.raise_not_implemented_error("_delete_content")

    def string_metadata(self):
        """
        Return the XML metadata for this container as a string.
        """
        return str(self)


class RepoCollection(Collection):
    """
    This is a model of a SWORD Collection.
    A collection comprises a number of containers - each corresponding to a deposited entity.
    """
    allow_generate_id = True

    # Add the raise_not_implemented error function to this class.
    raise_not_implemented_error = raise_not_implemented_error_for_method


    def _generate_container_id(self):
        """
        Unique UUID generator for collections without slugs.

        As these are UUIDs it is going to be almost impossible for it not to be unique, but it will loop until
        it finds a unique UUID for a collection just incase.

        :return: Unique ID for a container for this collection
        """
        id = str(uuid4())
        while self.container_exists(id):
            id = str(uuid4())
        return id

    def __init__(self, data, id):
        """
        Simple collection model with ID.

        :param data: XML data for a collection if needed
        :param id: ID for this collection
        """
        super().__init__(data)
        self.id = id

    def create_container(self, id=None):
        """
        Public method for _create_container_with_id

        Simply generates an ID incase one is not given, then creates the container

        :param id: ID for this container [OPTIONAL]

        :return: Deposit container or None
        """
        if not id and self.allow_generate_id:
            id = self._generate_container_id()
        return self._create_container_with_id(id)

    def _create_container_with_id(self, id=None):
        """
        This method should be implemented to create a container (and relevant persistent data) for a new deposit, with
        the given id or an ID generated by act of creating container.

        :param id: ID for this new container [OPTIONAL] - If None, then the function must generate an ID

        :return RepoContainer derivative if successfully created, None otherwise.
        """
        self.raise_not_implemented_error("_create_container_with_id")

    def deposit_binary(self, stream, filename, id=None):
        """
        Binary deposit method for a collection.

        :param stream: Stream like data
        :param filename: Filename for this stream
        :param id: ID if needed, otherwise one will be generated

        :return: RepoContainer or derivative
        """
        container = self.create_container(id)
        if container:
            container.add_or_replace_binary_file(stream, filename)
        return container

    def deposit_metadata(self, entry, id=None):
        """
        Metadata deposit for a collection.

        :param entry: Entry data
        :param id: ID if needed, otherwise one will be generated

        :return: RepoContainer or derivative
        """
        container = self.create_container(id)
        if container:
            container.add_or_replace_metadata(entry)
        return container

    def deposit_metadata_and_file(self, entry, stream, filename, id=None):
        """
        Deposit both the stream and the metadata.

        This is used for multipart deposits. It does the following:
        * Deposits the file stream and creates the container
        * Adds metadata to the container.

        :param entry: Entry data
        :param stream: Stream like data
        :param filename: Filename for stream
        :param id: ID if needed, otherwise one will be generated

        :return: RepoContainer derivative
        """
        repo_container = self.deposit_binary(stream, filename, id)
        repo_container.add_or_replace_metadata(entry)
        return repo_container

    @property
    def containers(self):
        """
        List the contents of this collection.

        :return: All the containers in the collection
        """
        self.raise_not_implemented_error("list")

    def get_container(self, id):
        """
        Get a container with a specific id.

        :param id: ID of container to attempt to get

        :return: RepoContainer derivative, or None if not found.
        """
        self.raise_not_implemented_error("get_container")

    def container_exists(self, id):
        """
        whether a given container exists.

        :param id: possible id for a container

        :return: Boolean on whether a container with the given id exists
        """
        self.raise_not_implemented_error("container_exists")

    def delete(self):
        """
        Delete this collection (and all the containers).
        """
        self.raise_not_implemented_error("delete")

    @staticmethod
    def _get_last_updated_from_list_of_containers(containers):
        """
        From a list of containers, get the updated date of the last updated container.

        :param containers: List of containers (probably generated by self.list())

        :return: Most recent last_updated string
        """
        last_updated = None
        if containers:
            # Sort the containers by updated value, then retrieve the updated value from the most recent.
            last_updated = sorted(containers, key=lambda container: container.updated, reverse=True)[0].updated
        return last_updated

    def to_feed(self):
        """
        Change this collection into an atom:feed XML document.

        Atom feeds are a list of atom:entry documents (our containers) with data on when it was last updated and
        the title of the container.

        https://validator.w3.org/feed/docs/atom.html

        :return: atom:feed XML document representing this collection
        """
        feed = Feed()
        feed.title = f"Collection: '{self.id}'"
        containers = self.containers
        feed.updated = self._get_last_updated_from_list_of_containers(containers)
        feed.entries = containers
        desc = current_app.config.get("FEED_DESCRIPTION")
        if desc:
            feed.description = desc
        return feed

    def to_xml_collection(self, link):
        """
        Create a Collection of this RepoCollection and add information relevant for a SWORD service document

        This can be overridden if someone would want to provide more information for their service document.

        :param link: URL for this collection - will be calculated in the request.

        :return: Collection element with relevant SWORD service document data
        """
        collection = Collection()
        collection.link = link
        collection.set_accept_elements()
        collection.packaging = "http://purl.org/net/sword/package/SimpleZip"
        return collection


class Repository:
    """
    Template repository class.

    Lists collections for this repository. Can also create collections and get collections.

    (Note that create_collection is not available as a flask endpoint)
    """

    # Add the raise_not_implemented error function to this class.
    raise_not_implemented_error = raise_not_implemented_error_for_method

    @property
    def collections(self):
        """
        List all collections for this repository.

        :return: List of RepoCollection derivatives
        """
        self.raise_not_implemented_error("collections")

    def collection_exists(self, id):
        """
        Check whether a given collection exists.

        :param id: Possible id for a collection

        :return: whether a RepoCollection with the given id exists
        """
        self.raise_not_implemented_error("collection_exists")

    def get_collection(self, id):
        """
        Attempt to get a collection with a specific id.

        :param id: Collection id

        :return: RepoCollection derivative or None
        """
        self.raise_not_implemented_error("get_collection")

    def create_collection(self, id, data=None):
        """
        Create a collection with XML data if needed.

        :param id: new collection id
        :param data: XML collection data
        """
        pass

    def delete_collection(self, id):
        """
        Delete the collection with a given ID.

        :param id: Collection id to delete
        """
        pass


class FileRepository(Repository):
    """
    Directory based store for collections and containers
    """

    def __init__(self, dir):
        """
        Create a new repository with a given directory.

        Will create the folder for the repo if it needs to.

        :param dir: Directory for the repository files
        """
        if not os.path.exists(dir):
            os.makedirs(dir)
        self.dir = dir

    def _path(self, id):
        """
        Simple function to join a collection id with the directory.

        :param id: Collection id

        :return: Joined repository directory with the collection id
        """
        return os.path.join(self.dir, id)

    @property
    def collections(self):
        """
        List all the collections in the directory as FileCollections.

        :return: List of FileCollections
        """
        return [self.get_collection(dir) for dir in os.listdir(self.dir)]

    def collection_exists(self, id):
        """
        Check whether the path exists at "self.dir/id".

        :param id: Collection id

        :return: Whether the path (and therefore the collection) exists at self.dir/id
        """
        return os.path.exists(self._path(id))

    def get_collection(self, id):
        """
        Get a collection as a FileCollection instance.

        :param id: Collection id

        :return: FileCollection if the collection exists, else None
        """
        path = self._path(id)
        collection = None
        if os.path.exists(path):
            collection = FileCollection(path)
            collection.atom_title = id
            collection.set_accept_elements()
        return collection

    def create_collection(self, id, **kwargs):
        """
        Create a collection with a given id.

        :param id: Collection id to give the new collection

        :return: Collection if created, None if it exists
        """
        collection = None
        path = self._path(id)
        if not os.path.exists(path):
            os.makedirs(path)
            collection = self.get_collection(id)
        return collection

    def _clean_dir(self):
        """
        Helper test function to clean the directories (delete the repository).
        """
        shutil.rmtree(self.dir)
        os.makedirs(self.dir)


class FileCollection(RepoCollection):

    def __init__(self, dir):
        """
        Initialize the collection with its directory.

        We don't initialize any XML data into this Collection as there's little reason
        to save the collection data as XML.

        In more complex repositories it may be worth saving this and making a _load_from_file method
        like in FileContainer.

        :param dir: Dir to use when finding containers related to this collection
        """
        super().__init__(None, os.path.basename(dir))
        self.dir = dir

    @property
    def containers(self):
        """
        List all the FileContainers in the directory.
        """
        return [self.get_container(id) for id in os.listdir(self.dir)]

    def _path(self, id):
        """
        Simple path joining for finding FileContainers in the FileCollection.

        :param: Container id
        :return: Joined directory and id path
        """
        return os.path.join(self.dir, id)

    def container_exists(self, id):
        """
        Check whether a container exists or not by seeing if the path has been created.

        :param id: Container id

        :return: whether the path of the container exists (True or False)
        """
        return os.path.exists(self._path(id))

    def get_container(self, id):
        """
        Get a container and check whether it exists. If it does, give a FileContainer instance.

        :param id: Id to get

        :return: FileContainer if container exists, else None
        """
        path = self._path(id)
        file_container = None
        if os.path.exists(path):
            file_container = FileContainer(path)
            file_container.title = id
        return file_container

    @staticmethod
    def _create_directory_for_container(path):
        """
        Create a directory for the container.

        :param path: Path to create the directory

        :return: True if we created a directory, False if directory already exists
        """
        success = False
        if not os.path.exists(path):
            os.makedirs(path)
            success = True
        return success

    def _create_container_with_id(self, id=None):
        """
        Create a directory for a container with a given ID, then return a FileContainer instance.

        :param id: ID for this container

        :return: FileContainer if directory is successfully created, None if it already existed.
        """
        path = self._path(id)
        file_container = None
        if self._create_directory_for_container(path):
            file_container = FileContainer(path)
        return file_container

    def delete(self):
        """
        Delete this collection.

        :return: True if this collection does not exist anymore on the file system, else False.
        """
        if os.path.exists(self.dir):
            shutil.rmtree(self.dir)
        return not os.path.exists(self.dir)


class FileContainer(RepoContainer):
    """
    Implementation of a container using a directory as the container.

    The ".entry.atom" file is where the metadata is stored.

    The ".completed" file exists only when the FileContainer is not in progress anymore.
    """
    @property
    def file(self):
        """
        Simple property that returns the path for this atom entry.
        """
        return self._path(".entry.atom")

    def _load_metadata_from_file(self):
        """
        Attempt to load metadata from the file property. If it doesn't exist, create it.
        """
        if os.path.exists(self.file):
            with open(self.file, "r") as entry_file:
                super()._load_metadata(entry_file.read())
        else:
            # If it doesn't exist, create it.
            self._store_metadata()

    def __init__(self, dir):
        """
        Initialize the entry with nothing, and load from file if needed.

        Set the directory location of this container for easy access.

        :param dir: Directory location of this FileContainer
        """
        super().__init__(None, os.path.basename(dir))
        self.dir = dir
        self._load_metadata_from_file()

    def _path(self, id):
        """
        Simple path join for the contents of this FileContainer.

        :param id: id of objects in the container

        :return: Joined path of container directory and id
        """
        return os.path.join(self.dir, id)

    @property
    def contents(self):
        """
        List of files in this directory. (Is a list of the file's name rather than file streams.)

        Only takes things that are not hidden (prefixed with '.' in linux) to avoid listing the .entry.atom file.
        """
        return [os.path.basename(name) for name in glob.glob(os.path.join(self.dir, "*"))]

    def get_file_content(self, filename):
        """
        Get content with a given filename.

        :param filename: Filename to find

        :return: File stream if file exists, else None
        """
        content = None
        path = self._path(filename)
        if os.path.exists(path):
            content = open(path, 'rb')
        return content

    def _store_metadata(self):
        """
        Store the metadata in this container.
        """
        with open(self.file, "w") as entry_file:
            entry_file.write(self.string_metadata())

    def _store_binary_file(self, stream, filename, is_derived=False):
        """
        Store a new binary file into this FileContainer.

        :param stream: File to deposit
        :param filename: Filename of stream
        :param is_derived: Whether this deposit was derived
        """
        with open(self._path(filename), "wb") as open_file:
            open_file.write(stream.read())

    @property
    def in_progress(self):
        """
        whether the '.completed' file exists - this only exists when the in_progress value is changed.

        This is always True until the '.completed' file is created during complete_deposit.

        :return: True if the .completed file exists, else False
        """
        return not os.path.exists(self._path(".completed")) and os.path.exists(self.dir)

    @in_progress.setter
    def in_progress(self, value):
        """
        Set the in_progress value.

        This needs a setter as otherwise the self.in_progress = True in the super() of __init__ will throw an error.

        :param value: Should be True or False. if False, add the file.

        If the container has been deleted, this will do nothing (as otherwise it would throw an error.)
        """
        # Just create the .completed file
        if not value and os.path.exists(self.dir):
            with open(self._path(".completed"), "w") as open_file:
                open_file.write('')

    def delete(self):
        """
        Delete this entry by simply clearing the directory.

        :return: whether the directory relating to this container exists or not
        """
        if os.path.exists(self.dir):
            shutil.rmtree(self.dir)
        return not os.path.exists(self.dir)

    def _delete_content(self, filename=None):
        """
        Delete some content in this FileContainer.

        :param filename: Filename of the file. If None, will delete ALL content.

        :return: whether it was successful.
        """
        if not filename:
            success = True
            for content in self.contents:
                path = self._path(content)
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
        else:
            path = self._path(filename)
            success = os.path.exists(path)
            if success:
                os.remove(path)
        return success
