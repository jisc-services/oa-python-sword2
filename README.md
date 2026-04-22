# SWORD2 Server and Client

## Public release
[Jisc](https://jisc.ac.uk/) released this repository into the public domain under the [GNU General Public License](https://www.gnu.org/licenses/gpl-3.0.en.html) in April 2026 following the decision to retire the Publications Router service on 1 July 2026.

It is one of [three Jisc git repositories](https://github.com/jisc-services/oa-PubRouter-App/blob/main/docs/Git_repos.md) that together store the complete application source code of the final operational version of Publications Router. 

This repository contains a library of source code that implements a SWORD2 client and server.  

## Archived & no longer supported

The repository is archived.
The source code is not supported or maintained by Jisc.  Issues and Pull Requests will not be monitored or responded to.

## Overview
The [SWORD2](http://swordapp.github.io/SWORDv2-Profile/SWORDProfile.html) protocol was developed to facilitate the exchange of data (including metadata and documents) between scholarly systems (e.g. repositories) to assist the automated distribution/dissemination of academic research outputs. 

This repository contains Jisc's implementation of:
* an HTTP client for SWORD2
* a SWORD2 server for storing documents and other items.

These library components have been developed using the [Flask framework](https://flask.palletsprojects.com/) and are dependent on being used in a Flask application context.

For extra information, see the [SWORD2 profile](http://swordapp.github.io/SWORDv2-Profile/SWORDProfile.html). The third section, 'Terminology' is particularly useful for learning about SWORD2 terms.

For a quick reference, the following terminology is also used to refer to parts of the SWORD2 spec:
* Collection: A Collection for deposits
* Container: A container for a deposit
* Entry: An atom:entry XML document

Whenever the 'EM' IRI is referenced, it is also referring to the 'Content' IRI.

The SWORD2 specification itself is [here](http://swordapp.org/sword-v2/sword-v2-specifications/).

## SWORD2 Client

The SWORD2 client implements most of the sword spec with reference to the Col, EM, Edit and SE IRIs. It does not implement the Content-MD5 checks, or use the On-Behalf-Of SWORD2 header.

### Examples

Here is an example with an initial zip deposit, followed by an addition of a text file and a metadata file.
```python
from sword2_client.client import SwordClient
from sword2_client.models import Entry

eprints = SwordClient(
	"http://eprints.pubrouter.jisc.ac.uk/id",
	"contents",
	{"username": "pubrouter": "password": "jisc"}
)

# Deposit zip file
with open("my_zip_file.zip", "rb") as file:
	# Setting in_progress to True, tells the server that further related actions (such as depositing associated metadata entry or another content file) are expected
	receipt = eprints.file_deposit("my_zip_file.zip", file, in_progress=True)
	

# Add some more content
with open("my_text_file.txt", "rb") as file:
	# This uses the EM-IRI from the previous deposit receipt
	eprints.add_file("my_text_file.txt", file, in_progress=True, deposit_receipt=receipt)

# Add some metadata
with open("my-atom-doc.xml", "rb") as file:
	entry = Entry(file.read())
	# This uses the SE-IRI from the previous deposit receipt
	# Since in_progress is not specified, it defaults to False, and so the deposit is finalised.
	eprints.add_metadata(entry, deposit_receipt=receipt)
```

## SWORD2 Server

The SWORD2 server package is an implementation of a SWORD2 server using Flask. This includes a Flask blueprint that can be used standalone or configured and added to other Flask applications.

The Flask blueprint includes all of the SWORD2 endpoints and will work using an implemented Repository model. 

The SWORD2 server implementation is intended to be as permissive as possible. For example, it will accept a multipart/form-data request in place of multipart/related, and does not need a set Content-Type header for a metadata deposit (it will assume application/atom+xml).

You can also use multipart/form-data for content deposits, as long as the Content-Disposition header is formatted correctly with the key 'attachment'.

It implements all of the SWORD IRIs, but may miss some functionality defined in the sword spec with the term 'MAY' or 'SHOULD'.

The following SWORD2 standards are not supported:
* The On-Behalf-Of header
* The Content-MD5 header

### Packaging support

There is little support for different types of packages on the server. It will return any package as SimpleZip, and it is up to the repository on how to process the zip files. This is so the implementation of the server can be simplified.

It is also possible to implement package handling code inside the repository implementations as they have access to the Flask `request` global.

## Implementing and configuring the SWORD2 server

The following classes should be implemented in the application:

* sword2.server.repository.RepoEntry - This is a SWORD container, which stores files and metadata and provides a means of accessing them
* sword2.server.repository.RepoCollection - This is a SWORD collection, which holds a list of containers
* sword2.server.repository.Repository - This implements a repository, which manages the storage of collections and provides the means for creating/updating/deleting collections and their contents.
* sword2.server.auth.SwordAuthBase - (OPTIONAL) For providing a mechanism for clients to authenticate against the server

There are also the following IMPORTANT configuration variables that MUST be inside your Flask application's app.config:

* *REPO_IMPL* - The module string for the repository implementation. By default, this is 'sword2.server.repository.FileRepository'.
* *REPO_ARGUMENTS* - A list of repo constructor arguments to be passed to your repository implementation on initialization of the repository.

The following variables are OPTIONAL.

* *AUTH_IMPL* - The module string for the repository implementation. By default, this is 'sword2.server.auth.SwordNoAuthentication'.

The rest of the variables are for the messages class - These are used for customizable messages:

* *NO_FILE_ERROR* - This is returned when there was no request data - no multipart files or request body.
* *DATA_WAS_NOT_XML_ERROR* - This is when the server expected an XML document of some kind but the data was not xml or was nothing.
* *DID_NOT_FIND_FILE_ERROR* - This is when the server attempted to find a file but it did not exist. This is a format string with one variable (filename).
* *UNKNOWN_ERROR* - This is used when something completely unpexected happens.
* *NOT_AUTHED_ERROR* - This is when a request fails to authenticate.
* *IN_PROGRESS* - This is used say that the deposit is still in progress in the deposit receipt.
* *DEPOSIT_COMPLETE* - This is used to say that the deposit is complete in the deposit receipt.
* *BAD_MULTIPART_ERROR* - This is when the server thought the request was a multipart request, but the 'payload' file of the multipart request did not exist.

### Repository

The Repository model must implement the following methods:

* `collections` - List all collections in this repository
* `get_collection` - Get a collection with a specific ID
* `collection_exists` - Whether or not a collection with a specific ID exists

The following methods are optional:

* `delete_collection` **OPTIONAL** - Delete a collection with a specific ID
* `create_collection` **OPTIONAL** - Create a collection with a specific ID

You must implement a repository class that at least implements the `collections` method, the `get_collection` method and the `collection_exists` method. The other two methods to create and delete collections are not needed, but are useful if you would like to be able to create collections via a custom admin endpoint or the like.

Some implementations may prefer to have only one collection for SWORD, and in that case it may be useful to simply return a list with one named value (like `["my_collection"]`) with the `get_collection` endpoint simply checking for that id.

The Col-IRI generated for this will be in the form **/collections/<collection_name>**.

### RepoCollection

The RepoCollection model must implement the following methods:

* `list` - List of all containers in this Collection
* `_create_container_with_id` - Create a container with a given ID
* `get_container` - Get a deposit container with a certain ID
* `container_exists` - Check whether a container with a given ID exists

The following method is optional:

* `delete` **OPTIONAL** - Delete this collection

The others methods are for debugging purposes or should be implemented as administrator endpoints.

### RepoContainer

This does all the heavy lifting for a deposit container and is also the metadata object.

A child of RepoContainer needs to implement the following methods:

* `_store_metadata` - Store given metadata into the container so it persists between deposits
* `_store_binary_file` - Store a given file stream into the container so it persists between deposits
* `_delete_content` - Delete content with a given filename from the deposit container
* `get_file_content` - Get file content from this container
* `contents` - List all contents in this deposit container
* `delete` - Delete the whole container
* `_process_completed_deposit` **OPTIONAL**- Processes the deposit after a deposit is finished
* `in_progress` **OPTIONAL** - A getter and setter indicates a deposit is complete or not (this *MAY* be persisted if you want to implement a system which completes deposits on a scheduled basis rather at the time the SWORD calls are made.)

The child class may also override other methods.

### SwordAuthenticationBase

This doesn't have to be implemented and will use `sword2.server.auth.SwordNoAuthentication` by default.

If implemented, this needs to implement the following methods:

* `valid_credentials` - Given the collection id and the container id, check whether the credentials are valid or not.

with `valid_credentials` you will also have access to the Flask request context, so things like *Flask-Login*'s `current_user` global or `current_app` will be accessible in these functions.

If you would like to do something else, you can use Flask's '@blueprint.before_request' decorator to circumvent the Auth Class, but it is not recommended.

### Adding as a blueprint for a Flask app

After setting the correct config in your Flask app and implementing the above classes, the blueprint can be added to the server like so:

```python
from flask import Flask
from sword2.server.views.blueprint import sword

# Add my own repository implementation
app.config["REPO_IMPL"] = "myrepo.repository.MyRepository"
# Add the SWORD2 blueprint to the Flask app so it can use SWORD2
app.register_blueprint(sword, url_prefix="/sword")
```

The SWORD2 endpoints will then work with your implementation of the `Repository` model.

## Fully coded working sample
A working implementation using this library as both a client and a server may be found in the PubRouter application - see repository https://github.com/jisc-services/oa-PubRouter-App.  

Within that repository...
* a SWORD client is implemented using code in: [./src/router/jper_sword_out](https://github.com/jisc-services/oa-PubRouter-App/tree/main/src/router/jper_sword_out)  (overview [documentation](https://github.com/jisc-services/oa-PubRouter-App/tree/main/docs/sword-out)). This code can be run as a separate linux process e.g. via _supervisorctl_ (look for file "sword-out.conf" in the _deployment_ directory) or as a subroutine to the scheduler process (look at file: scheduler.py).
* a SWORD server is implemented using code in: [./src/router/jper_sword_in](https://github.com/jisc-services/oa-PubRouter-App/tree/main/src/router/jper_sword_in). Note that you will need to be familiar with deployment of applications being run in linux via _supervisorctl_ to fully understand this code - it is suggested you search the oa-PubRouter-App repository for file: "sword-in.conf" (in the _deployment_ directory) and string "REPO_IMPL" (in that repository and this one) as a way into the code.

