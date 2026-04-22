"""
This is all the blueprint related code for SWORD2 server endpoints to be used with a Flask App.

This creates a blueprint that can then be imported later and used with a developer's Repository implementation.

The main IRI routes (other than service_document) use a respective controller in sword2.server.controllers.

They map as:
    collection_iri -> sword2.server.controllers.collection
    edit_iri (Edit-IRI and SE-IRI)-> sword2.server.controllers.edit
    em_iri (EM-IRI and Cont-IRI) -> sword2.server.controllers.edit_media
"""
from sword2.models import ServiceDocument, DepositReceipt, Link, Entry, guess_type
from sword2.server.globals import repository, messages, auth, current_app
from sword2.server.controllers.collection import CollectionRequest
from sword2.server.controllers.edit import EditRequest
from sword2.server.controllers.edit_media import EditMediaRequest
from sword2.server.util import atom_response, get_container_or_error, atom_error
from flask import Blueprint, url_for, request, make_response, Response


sword = Blueprint("sword2-server", __name__)


@sword.route("/")
def service_document():
    """
    Service document endpoint.

    Will load a simple service document with all available collections as listed by the repository.
    """
    auth.authenticate()
    service_document = ServiceDocument()
    service_document.version = "2.0"
    service_document.title = current_app.config.get("SWORD_SERVER_TITLE", "Python SWORD2 Server")
    collections = []
    for collection in repository.collections:
        url = url_for(".collection_iri", collection_id=collection.id, _external=True)
        collections.append(collection.to_xml_collection(url))
    service_document.collections = collections
    return atom_response(service_document)


def _create_links(container, collection_id):
    """
    Create links for all files listed in a container, and add the required IRIs

    All of these links are created with _external=True, which will add the full URL of the link to the xml elements

    Without _external=True, the url doesn't include the domain - it would just be a relative path:
        _external=False: /collections/id/id
        _external=True: https://mywebsite.com/collections/id/id

    :param container: RepoContainer derivative - includes atom:entry metadata
    :param collection_id: Collection referring to this data

    :return: List of links for a DepositReceipt
    """
    links = []
    iris = [
        # ("endpoint", "rel-value")
        ("edit_iri", "edit"),   # Edit-IRI
        ("em_iri", "edit-media"),   # EM-IRI
        ("edit_iri", "http://purl.org/net/sword/terms/add"),    # SE-IRI
    ]
    for _endpoint, _rel in iris:
        iri_link = Link()
        iri_link.rel = _rel
        iri_link.href = url_for(
            f".{_endpoint}", collection_id=collection_id, container_id=container.id, _external=True)
        links.append(iri_link)

    for filename, is_derived in container.current_request_contents:
        link = Link()
        link.rel = container.rel_value_dict[is_derived]
        link.mimetype = guess_type(filename)
        link.href = url_for(
            ".em_iri",
            collection_id=collection_id,
            container_id=container.id,
            resource_name=filename,
            _external=True
        )
        links.append(link)
    return links


def _create_deposit_receipt_from_container(container, collection_id):
    """
    Creates a DepositReceipt from a given container

    :param container: RepoContainer derivative - includes atom:entry metadata
    :param collection_id: Collection containing this data

    :return: DepositReceipt created from the given RepoContainer with added links
    """
    deposit = DepositReceipt(container)
    deposit.links = _create_links(container, collection_id)

    treatment = orig_file = ""
    derived_files = []
    if container.metadata_is_stored:
        treatment = "Stored metadata. "
    for filename, is_derived in container.current_request_contents:
        if is_derived:
            derived_files.append(filename)
        else:
            orig_file = filename
    if orig_file:
        derived = f", which was unpacked and these derived files were also stored: {', '.join(derived_files)}" if derived_files else ""
        treatment += f"Stored file: {orig_file}{derived}."
    if treatment:
        deposit.treatment = treatment
    deposit.verbose_description = messages.IN_PROGRESS if container.in_progress else messages.DEPOSIT_COMPLETE
    return deposit


@sword.route("/collections/<collection_id>", methods=CollectionRequest.valid_methods)
def collection_iri(collection_id=None):
    """
    Do collection_iri related requests (just POST)

    Methods:
        GET - Get an atom:feed representation of this collection
        POST - Create a new container for this collection

    Refer to sword2.server.controllers.collection for more information

    :param collection_id: Id for the collection
    """
    auth.authenticate(collection_id)
    collection = repository.get_collection(collection_id)
    if not collection:
        atom_error(messages.NO_COLLECTION_ERROR)
    controller = CollectionRequest(request.method)
    container_or_feed, status = controller(request, collection)
    headers = {}
    # This could be an atom:feed or an Entry - if it's an Entry, create a DepositReceipt out of it
    if isinstance(container_or_feed, Entry):
        container_or_feed = _create_deposit_receipt_from_container(container_or_feed, collection_id)
        headers = {
            "Location": container_or_feed.edit_iri
        }
    else:
        # Else, this is an atom:feed document - set the ID to be the unique URL for this collection
        # (this is allowed by AtomPub section 5.2)
        container_or_feed.id = url_for(".collection_iri", collection_id=collection_id, _external=True)
    return atom_response(container_or_feed, status, headers)


@sword.route("/collections/<collection_id>/<container_id>", methods=EditRequest.valid_methods)
def edit_iri(collection_id, container_id):
    """
    Do edit_iri (Edit-IRI and SE-IRI) related requests.

    Methods:
        GET - Retrieve the metadata for this container
        POST - (a) Update metadata; (b) Update metadata + Add new file content via Multipart request; (c) complete deposit.
        PUT - (a) Replace metadata; (b) Replace metadata + File content via a Multipart request; (c) complete deposit.
        DELETE - Delete the container & its contents

    Refer to sword2.server.controllers.edit for more information

    :param collection_id: Collection id related to this request
    :param container_id: Container of this request
    """
    auth.authenticate(collection_id, container_id)
    container = get_container_or_error(repository, collection_id, container_id)
    controller = EditRequest(request.method)
    container_or_str, status = controller(request, container)
    # If we have data, return a deposit receipt.
    if container_or_str:
        deposit = _create_deposit_receipt_from_container(container_or_str, collection_id)
        headers = {
            "Location": deposit.edit_iri
        }
        response = atom_response(deposit, status, headers)
    else:
        # If we don't have data, return an empty (204 NO CONTENT) response.
        response = make_response('', status)
    return response


@sword.route("/collections/<collection_id>/<container_id>/media", methods=EditMediaRequest.valid_methods)
@sword.route("/collections/<collection_id>/<container_id>/media/<resource_name>", methods=EditMediaRequest.valid_methods)
def em_iri(collection_id, container_id, resource_name=None):
    """
    Do em_iri (EM-IRI and Cont-IRI) related requests.

    Refer to sword2.server.controllers.edit_media for more information

    Methods:
        GET: (a) Retrieve the all content of container as a package; (b) Retrieve specified resource (file) from the container.
        POST: (a) Add individual file (binary content); (b) Add several files from a package (zipfile) to the container
        PUT: (a) Replace individual file (binary content); (b) Replace all files from a package (zipfile) in the container
        DELETE: Delete binary content (file) from the container (but NOT delete the container itself)

    :param collection_id: Collection id related to this request
    :param container_id: Container id related to this request
    :param resource_name: Resource name that will be requested (AKA filename)
    """
    auth.authenticate(collection_id, container_id)
    container = get_container_or_error(repository, collection_id, container_id)
    controller = EditMediaRequest(request.method)
    data, status = controller(request, container, resource_name)
    # If this returns entry data, create a deposit receipt.
    if isinstance(data, Entry):
        deposit = _create_deposit_receipt_from_container(container, collection_id)
        headers = {
            "Location": deposit.em_iri
        }
        return atom_response(deposit, status, headers)
    elif data:
        filename = resource_name or f"{container_id}.zip"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
        # Streamed file, send a Flask response of the data.
        return Response(data, mimetype=guess_type(filename), headers=headers, status=status)
    else:
        return Response('', status=status)
