"""
Sword related models - these are models of XML structures.

Collection - <app:collection>
ServiceDocument - <app:service>
Entry - <atom:entry>
Link - <atom:link>
DepositReceipt - <atom:entry>
ErrorDocument - <sword:error>

NOTE: The @property methods will directly refer to the XML element in a given schema. The schema for each namespace
can be found here:
    dcterms - http://dublincore.org/documents/dcmi-terms/
    atom - https://validator.w3.org/feed/docs/atom.html
    sword - http://swordapp.org
"""
from lxml import etree
import mimetypes


def guess_type(filename):
    """
    Guess a mimetype in case we need to do something with zip files
    """
    tuple_or_str = mimetypes.guess_type(filename)
    if isinstance(tuple_or_str, str):
        return tuple_or_str or "application/octet-stream"
    else:
        # guess_tuple will have first element of tuple set to None if the mime-type can't be guessed - in that
        # case return octet-stream as it's safe with binary data.
        return tuple_or_str[0] or "application/octet-stream"


# Generic model class - Other classes will inherit this
class SwordModel:
    """
    Wrapper for SWORD related XML documents
    This makes it easier to work with sword documents, while adding methods that can be used to
    create python models of XML documents to reduce need for XML manipulation when using the models.
    """
    # Root element name
    _root = "root"

    # Sword namespace list for use in finding sword-related elements
    all_namespaces = {
        "dcterms": "http://purl.org/dc/terms/",
        "sword": "http://purl.org/net/sword/terms/",
        "atom": "http://www.w3.org/2005/Atom",
        "app": "http://www.w3.org/2007/app"
    }

    # Default set of namespaces for this model
    _namespaces = {}

    def __init__(self, data=None):
        """
        Initialize the model with XML data if wanted.

        The if statement is in a priority order - Etree data is the most likely, then bytes from response data.
        SwordModels are next for when DepositReceipt's are created from Entry documents, then finally string data,
        which may be used when someone opens a file in 'r' mode rather than 'rb'.

        :param data: Some sort of XML related data - strings, bytes, other SwordModel instances, etree instances.
        """
        self.xml = None
        if data is not None:
            # Etree data - already what we want
            if isinstance(data, etree._Element):
                self.xml = data
            # Bytes data - happy to use by default. Will replace the root element to make sure the namespaces are correct
            elif isinstance(data, bytes):
                self.xml = self._replace_root(etree.fromstring(data))
            # SwordModel - take the xml attr
            elif isinstance(data, SwordModel):
                self.xml = data.xml
            # Str data - cast to bytes just in case it's UTF-8 as etree throws an error with Unicode data
            # Will replace the root element with the root element name defined in self._root, and make sure
            # it has the correct namespace
            elif isinstance(data, str):
                self.xml = self._replace_root(etree.fromstring(bytes(data, "utf-8")))
            # Otherwise, assume bad data
            else:
                raise ValueError("Given data was not a valid datatype for an XML document")
        # If it is None, make a default element.
        if self.xml is None:
            self.xml = etree.Element(self._root, nsmap=self._namespaces)

    @classmethod
    def create_unattached_element(cls, tagname, text='', **kwargs):
        """
        Create an element with no parent that has the same namespaces as this SwordModel.

        This can be used when setting a property that requires a namespaced tag - if using normal etree elements,
        the tag would be wrong when used with a SwordModel.

        ex:
        element = cls.create_unattached_element("atom:link", "url", attributes={})
        DepositReceipt.link = element

        :param tagname: Tagname in the form 'namespace:tagname' that will be namespaced.
        :param text: Text to add to the element.
        :param kwargs: Any keyword-arguments to apply to etree.Element

        :return: Correctly namespaced etree element
        """
        element = etree.Element(cls.tagname_to_namespaced_tagname(tagname), **kwargs)
        element.text = text
        return element

    @classmethod
    def _replace_root(cls, xml):
        """
        The only way to change the namespaces of an already initialized ETree instance is to replace the root
        element with a new one that has the correct namespaces.

        For example, DepositReceipts can be initialized from Entry instances but these have different namespaces.
        If you create an Entry, then from the Entry data create a DepositReceipt, this will still have the
        namespaces as an Entry instance.

        This will make a new root element and replace the current root when loading data, adding the required
        namespaces.

        :param xml: ETree instance

        :return: Copied ETree instance with new root element
        """
        new_root = etree.Element(cls._root, nsmap=cls._namespaces)
        for child in xml:
            new_root.append(child)
        return new_root

    @classmethod
    def _construct_namespace_tagname(cls, namespace, tagname):
        """
        Create a namespaced tagname, of general format "{http://namespace/uri}tagname".

        :param namespace: Namespace name to use (like dcterms, atom)
        :param tagname: Tag name to apply the formatting to

        If the namespace doesn't exist (it's not a sword namespace), just return the tag.
        """
        namespace = cls.all_namespaces.get(namespace)
        # Construct qualified namespaced tagname if namespace exists, otherwise simply return tagname
        return f"{{{namespace}}}{tagname}"

    @classmethod
    def tagname_to_namespaced_tagname(cls, tagname):
        """
        Given a tagname in the form 'namespace:tagname', replace the namespace with a namespaced URL.

        (e.g: sword:error -> {http://purl.org/net/sword/terms}error)

        :param tagname: Tagname to namespace

        :return: tagname with url namespace, or just the tagname if there was no namespace.
        """
        first, _, last = tagname.partition(":")
        # If tagname is of form: "namespace:tagname" then convert to qualified form, otherwise simply return tagname
        return cls._construct_namespace_tagname(first, last) if last else tagname

    def merge(self, etree_instance):
        """
        Will merge the direct children of a SwordModel and an etree instance together.

        It will prefer members of the etree_instance rather than this SwordModel.

        :param etree_instance: Etree instance of XML document to merge
        """
        # This must be done to avoid duplicating elements.
        # The isinstance code must also be done as some of these will be comments - in the case of a comment,
        # the element's tag is not a string (which will cause an error in etree_instance.findall.)
        qualified_tagnames = set(element.tag for element in etree_instance if isinstance(element.tag, str))
        for qualified_tagname in qualified_tagnames:
            self.delete_elements_matching_tagname(qualified_tagname)
            self.create_elements_with_xml_instance_list(etree_instance.findall(qualified_tagname))

    def get_element(self, abbrev_tagname, return_text=False):
        """
        Get an element from the xml corresponding to a given tagname.

        :param abbrev_tagname: in shorthand colon separated form: "namespace:tag" (e.g. "atom:title")
        :param return_text: Get in text format (True) or as the class' default model (like SwordModel) (False)

        :return: SwordModel of element or text if found, else None
        """
        qualified_tagname = self.tagname_to_namespaced_tagname(abbrev_tagname)
        # found = self.xml.find(f".//{qualified_tagname}")
        found = self.xml.find(qualified_tagname)
        if found is not None:
            return found.text if return_text else found
        return None

    def get_elements_list(self, abbrev_tagname, return_text=False):
        """
        Get all elements corresponding to the given tagname.

        :param abbrev_tagname: in shorthand colon separated form: "namespace:tag" (e.g. "atom:title")
        :param return_text: Get in text format (True) or as the class' default model (like SwordModel) (False)

        :return: list of elements or text if found, else an empty list
        """
        qualified_tagname = self.tagname_to_namespaced_tagname(abbrev_tagname)
        # return [element.text if return_text else element for element in self.xml.findall(f".//{qualified_tagname}")]
        return [element.text if return_text else element for element in self.xml.findall(qualified_tagname)]

    def delete_elements_matching_tagname(self, qualified_tagname, only_direct_children=True):
        """
        Delete all elements with specified tagname.

        This will find all the elements with that tagname, and then delete them.

        :param qualified_tagname: Tag name to delete
        :param only_direct_children: True: delete direct children with the matching tagname;
                                     False: delete all children with the matching tagname.
        """
        find_string = qualified_tagname if only_direct_children else f".//{qualified_tagname}"
        for element in self.xml.findall(find_string):
            element.getparent().remove(element)

    def delete_elements_matching_value(self, abbrev_tagname, value, just_first=True, only_direct_children=True):
        """
        Delete all or first element(s) with specified tagname and value..

        This will find all the elements with that tagname and delete those with matching value.

        :param abbrev_tagname: in shorthand colon separated form: "namespace:tag" (e.g. "atom:title")
        :param value: value to delete
        :param just_first: Boolean - True: delete at most 1 element; False: delete all elements matching value
        :param only_direct_children: True: delete direct children with the matching tagname;
                                     False: delete all children with the matching tagname.
        """
        qualified_tagname = self.tagname_to_namespaced_tagname(abbrev_tagname)
        find_string = qualified_tagname if only_direct_children else f".//{qualified_tagname}"
        for element in self.xml.findall(find_string):
            if element.text == value:
                element.getparent().remove(element)
                if just_first:
                    return

    def get_element_with_value(self, abbrev_tagname, value, only_direct_children=True):
        """
        Return first element matching value, or None.

        :param abbrev_tagname: in shorthand colon separated form: "namespace:tag" (e.g. "atom:title")
        :param value: value to delete
        :param only_direct_children: True: delete direct children with the matching tagname;
                                     False: delete all children with the matching tagname.
        """
        qualified_tagname = self.tagname_to_namespaced_tagname(abbrev_tagname)
        find_string = qualified_tagname if only_direct_children else f".//{qualified_tagname}"
        for element in self.xml.findall(find_string):
            if element.text == value:
                return element
        return None
    
    
    @classmethod
    def _always_list(cls, maybe_list):
        """
        Make sure that the given parameter always returns a list

        :param maybe_list: Either a singular value or a list

        :return: The original list if maybe_list was a list, else put maybe_list inside a list and return that
        """
        return maybe_list if isinstance(maybe_list, list) else [maybe_list]

    def _get_qualified_tagname_and_delete_elements_matching_tagname(self, abbrev_tagname):
        """
        Helper function that generates a qualified tagname from an abbreviated tagname, and also deletes
        all elements with the given tagname.

        :param abbrev_tagname: Tagname in the form namespace:name

        :return: Qualified tagname in the form {namespace_url}name
        """
        qualified_tagname = self.tagname_to_namespaced_tagname(abbrev_tagname)
        self.delete_elements_matching_tagname(qualified_tagname)
        return qualified_tagname

    def set_elements_with_xml_instance_list(self, abbrev_tagname, xml_list):
        """
        Set a list of elements by a list of ETree or SwordModel objects (this first DELETES any existing elements
        that match the tagname).

        :param abbrev_tagname: Tagname in the form namespace:name
        :param xml_list: a single instance or list of ETree/SwordModel objects
        """
        self._get_qualified_tagname_and_delete_elements_matching_tagname(abbrev_tagname)
        self.create_elements_with_xml_instance_list(xml_list)

    def set_elements_with_values_list(self, abbrev_tagname, values):
        """
        Set a list of elements by text value (this first DELETES any existing elements
        that match the tagname).

        :param abbrev_tagname: Tagname in the form namespace:name
        :param values: a single instance or list of text values to create elements with
        """
        qualified_tagname = self._get_qualified_tagname_and_delete_elements_matching_tagname(abbrev_tagname)
        self.create_elements_with_values_list(qualified_tagname, values)

    def add_elements_with_values_list(self, abbrev_tagname, values):
        """
        Set a list of elements by text value

        :param abbrev_tagname: Tagname in the form namespace:name
        :param values: a single instance or list of text values to create elements with
        """
        self.create_elements_with_values_list(self.tagname_to_namespaced_tagname(abbrev_tagname), values)

    def set_element_with_xml_instance(self, abbrev_tagname, xml):
        """
        Create and set an element with an ETree or SwordModel instance (this first DELETES any existing elements
        that match the tagname)

        :param abbrev_tagname: Tagname in the form namespace:name
        :param xml: ETree or SwordModel instance to add to this XML document
        """
        self._get_qualified_tagname_and_delete_elements_matching_tagname(abbrev_tagname)
        self.create_element_with_xml_instance(xml)

    def set_element_with_value(self, abbrev_tagname, value, attributes=None):
        """
        Create and set an element with a text value and given attributes

        :param abbrev_tagname: Tagname in the form namespace:name
        :param value: Text value to set for the new element
        :param attributes: Attributes dictionary to add to the new element
        """
        qualified_tagname = self._get_qualified_tagname_and_delete_elements_matching_tagname(abbrev_tagname)
        self.create_element_with_value(qualified_tagname, value, attributes)

    def add_element_with_value(self, abbrev_tagname, value, attributes=None):
        """
        Create an element using an abbreviated tagname instead of a qualified one.

        :param abbrev_tagname: Tagname in the form namespace:name.
        :param value: Text value to set for the new element.
        :param attributes: Attributes dictionary to add to the new element.
        """
        qualified_tagname = self.tagname_to_namespaced_tagname(abbrev_tagname)
        self.create_element_with_value(qualified_tagname, value, attributes)

    def create_element_with_value(self, qualified_tagname, value, attributes=None):
        """
        Create an element with a given tagname, text value and attributes.

        :param qualified_tagname: Tagname in the form {namespace_url}name
        :param value: Text value to set for the new element
        :param attributes: Attributes dictionary to add to the new element
        """
        
        xml = etree.Element(qualified_tagname, attrib=attributes)
        xml.text = value
        self.xml.append(xml)

    def create_element_with_xml_instance(self, xml):
        """
        Create an element from an XML instance (ETree or SwordModel).

        If the element is a SwordModel, it will add the ETree representation of the SwordModel.

        :param xml: XML Document (ETree or SwordModel)
        """
        if isinstance(xml, SwordModel):
            # Get the ETree from the SwordModel object
            xml = xml.xml
        self.xml.append(xml)

    def create_elements_with_xml_instance_list(self, xml_list):
        """
        Create elements from a singular instance or list of XML documents (ETree or SwordModel)

        The use of _always_list here wil convert a singular instance to a list of instances.

        :param xml_list: Singular instance or list of xml documents (ETree or SwordModel)
        """
        for xml in self._always_list(xml_list):
            self.create_element_with_xml_instance(xml)

    def create_elements_with_values_list(self, qualified_tagname, values):
        """
        Create elements from a singular or list of text values

        The use of _always_list here will convert a singular value to a list of values.

        :param qualified_tagname: tagname in the form {namespace_url}name
        :param values: Singular instance or list of values to create elements with
        """
        for value in self._always_list(values):
            self.create_element_with_value(qualified_tagname, value)

    def is_error(self):
        """
        Whether or not this model refers to errors.
        """
        return False

    @property
    def text(self):
        """
        Return the text of the element.

        :return: The text property of the xml stored in this model
        """
        return self.xml.text

    def xpath(self, xpath, **kwargs):
        """
        Wrapper for ETree's xpath method - adds namespaces to the xpath method so it doesn't need to be added
        every time.

        :param xpath: xpath string
        :param kwargs:
            Kwarg list can be seen in the following code:
            https://github.com/lxml/lxml/blob/7e7277b7ce85df9cb1507f3df0068cb52e71ae13/src/lxml/etree.pyx#L1559
            So kwargs are for XPATH variables.
        """
        return self.xml.xpath(xpath, namespaces=self.all_namespaces, **kwargs)

    def to_str(self, xml_declaration=False, pretty=False):
        return etree.tostring(self.xml, encoding="unicode", xml_declaration=xml_declaration, pretty_print=pretty)

    def __bytes__(self):
        """
        Return the xml data as a byte string to use as a file or a request body
        """
        return etree.tostring(self.xml, encoding="UTF-8", xml_declaration=True)

    def __str__(self):
        """
        Return the XML data as a normal string.
        """
        return self.__bytes__().decode("utf-8")


# -- The models below are implementations of actual defined XML structures --
# This means that most of the properties map to names of xml elements (although will have camelCase mapped to
# underscore_case when applicable).


class Collection(SwordModel):

    """
    Model for an <app:collection> element

    all these getters and setters will map to possible XML elements in the model, and generally have the same
    property names as the real tag name.
    """
    _root = SwordModel.tagname_to_namespaced_tagname("app:collection")

    _namespaces = {
        None: "http://www.w3.org/2007/app",
        "atom": "http://www.w3.org/2005/Atom",
        "sword": "http://purl.org/net/sword/terms/",
        "dcterms": "http://purl.org/dc/terms/"
    }

    @property
    def abstract(self):
        """
        This maps to a <dcterms:abstract> element.

        With a SwordCollection, this is actually used for the Collection Description rather than
        a publication abstract.
        """
        return self.get_element("dcterms:abstract", True)

    @abstract.setter
    def abstract(self, value):
        self.set_element_with_value("dcterms:abstract", value)

    @property
    def accept(self):
        """
        This maps to an <app:accept> element.

        These elements are for stating what content types are accepted by the SWORD2 Server.
        """
        accept = None
        for xml in self.get_elements_list("app:accept"):
            if xml.get("alternate") is None:
                accept = xml
                break
        return accept

    @property
    def accept_alternate(self):
        accept = None
        for xml in self.get_elements_list("app:accept"):
            if xml.get("alternate") is not None:
                accept = xml
                break
        return accept

    def set_accept_elements(self, **kwargs):
        """
        Set the <app:accept> elements. These could be done by manually creating XML, but it's much quicker
        to add these by using just text arguments, as the text value (the mimetype)
        of these is the only thing that changes.

        :param kwargs:
            accept: Mimetype that can be accepted on a binary/content/file deposit
            accept_alternate: Mimetype that can be accepted on a multipart deposit
        """
        accept_val = kwargs.get("accept", "*/*")
        accept_alternate_val = kwargs.get("accept_alternate", "*/*")
        accept_term = self._get_qualified_tagname_and_delete_elements_matching_tagname("app:accept")
        self.create_element_with_value(accept_term, accept_val)
        self.create_element_with_value(accept_term, accept_alternate_val, {"alternate": "multipart-related"})

    @property
    def link(self):
        return self.xml.get("href")

    @link.setter
    def link(self, value):
        self.xml.attrib["href"] = value

    @property
    def packaging(self):
        return self.get_elements_list("sword:acceptPackaging", True)

    @packaging.setter
    def packaging(self, values):
        self.set_elements_with_values_list("sword:acceptPackaging", values)

    @property
    def title(self):
        return self.get_element("atom:title", True)

    @title.setter
    def title(self, value):
        self.set_element_with_value("atom:title", value)


class ServiceDocument(SwordModel):

    """
    This maps to an <app:service> XML element.
    """

    _root = SwordModel.tagname_to_namespaced_tagname("app:service")

    _namespaces = {
        None: "http://www.w3.org/2007/app",
        "atom": "http://www.w3.org/2005/Atom",
        "sword": "http://purl.org/net/sword/terms/",
        "dcterms": "http://purl.org/dc/terms/"
    }

    def __init__(self, data=None):
        # This class needs an __init__ function as if there is no <app:workspace> element we'll get errors
        # when we list collections etc.
        # It's easier just to add one.
        super().__init__(data)
        if not data:
            # Create an <app:workspace> element in case the Collection doesn't have one, otherwise
            # we won't be able to add collections without errors
            self.set_element_with_value("app:workspace", "")

    @property
    def collections(self):
        """
        List all the <app:collection> elements as SwordModels for the collections in this service document.
        """
        return [Collection(model) for model in self.workspace.get_elements_list("app:collection")]

    @collections.setter
    def collections(self, values):
        """
        :param values: List of Collection models or etrees
        """
        self.workspace.set_elements_with_xml_instance_list("app:collection", values)

    @property
    def max_upload_size(self):
        return self.get_element("sword:maxUploadSize", True)

    @max_upload_size.setter
    def max_upload_size(self, value):
        """
        :param value: String upload size
        """
        self.set_element_with_value("sword:maxUploadSize", value)

    @property
    def services(self):
        return self.workspace.get_elements_list("sword:service")

    @property
    def title(self):
        return self.workspace.get_element("atom:title", True)

    @title.setter
    def title(self, value):
        """
        :param value: String title
        """
        self.workspace.set_element_with_value("atom:title", value)

    @property
    def version(self):
        """
        Sword version number - should likely be '2.0'.
        """
        return self.get_element("sword:version", True)

    @version.setter
    def version(self, value):
        """
        :param value: String sword version
        """
        self.set_element_with_value("sword:version", value)

    @property
    def workspace(self):
        """
        This must be a SwordModel as it will be used by other collection properties to set/get elements.
        """
        return SwordModel(self.get_element("app:workspace"))


class Entry(SwordModel):

    """
    This maps to an <atom:entry> XML element.
    """

    _root = SwordModel.tagname_to_namespaced_tagname("atom:entry")

    _namespaces = {
        None: "http://www.w3.org/2005/Atom",
        "dcterms": "http://purl.org/dc/terms/",
        "sword": "http://purl.org/net/sword/terms/"
    }

    @property
    def abstract(self):
        return self.get_element("dcterms:abstract", True)

    @abstract.setter
    def abstract(self, value):
        """
        :param value: String abstract text
        """
        self.set_element_with_value("dcterms:abstract", value)

    @property
    def access_rights(self):
        return self.get_elements_list("dcterms:accessRights", True)

    @access_rights.setter
    def access_rights(self, values):
        """
        :param values: String list of values or singular value
        """
        self.set_elements_with_values_list("dcterms:accessRights", values)

    @property
    def alternative(self):
        return self.get_element("dcterms:alternative", True)

    @alternative.setter
    def alternative(self, value):
        """
        :param value: String alternative text
        """
        self.set_element_with_value("dcterms:alternative", value)

    @property
    def authors(self):
        return self.get_elements_list("atom:author")

    @authors.setter
    def authors(self, values):
        """
        :param values: Author element tree instances or SwordModel instances - can be singular
        """
        self.set_elements_with_xml_instance_list("atom:author", values)

    # Object has an atom namespaced title and a dc namespaced title
    @property
    def atom_title(self):
        """
        The atom title will refer to the title of the Entry document, so likely the title of the deposit.
        """
        return self.get_element("atom:title", True)

    @atom_title.setter
    def atom_title(self, value):
        """
        :param value: String title text (atom:title)
        """
        self.set_element_with_value("atom:title", value)

    @property
    def available(self):
        return self.get_element("dcterms:available", True)

    @available.setter
    def available(self, value):
        """
        :param value: String available text
        """
        self.set_element_with_value("dcterms:available", value)

    @property
    def bibliographic_citation(self):
        return self.get_elements_list("dcterms:bibliographicCitation", True)

    @bibliographic_citation.setter
    def bibliographic_citation(self, values):
        """
        :param values: String list of citation text - can be singular
        """
        self.set_elements_with_values_list("dcterms:bibliographicCitation", values)

    @property
    def contributor(self):
        return self.get_element("dcterms:contributor", True)

    @contributor.setter
    def contributor(self, value):
        """
        :param value: Contributor text
        """
        self.set_element_with_value("dcterms:contributor", value)

    # entry has a dc and atom title
    @property
    def dc_title(self):
        """
        The dc title will refer to the tile of the publication.
        """
        return self.get_element("dcterms:title", True)

    @dc_title.setter
    def dc_title(self, value):
        """
        :param value: String title text (dcterms:title)
        """
        self.set_element_with_value("dcterms:title", value)

    @property
    def description(self):
        return self.get_element("dcterms:description", True)

    @description.setter
    def description(self, value):
        """
        :param value: String description text
        """
        self.set_element_with_value("dcterms:description", value)

    @property
    def has_part(self):
        """
        Gets all <dcterms:hasPart> values (can be > 1)
        :return: 
        """
        return self.get_elements_list("dcterms:hasPart", True)

    @has_part.setter
    def has_part(self, values):
        """
        Set (replaces) <dcterms:hasPart> values (can be > 1)
        :param values: String list of hasPart values - may be singular
        """
        self.set_elements_with_values_list("dcterms:hasPart", values)

    def add_part(self, value, allow_duplicates=False):
        """
        Add a dcterms:hasPart element
        :param value:
        :param allow_duplicates: Boolean - True: Allow duplicate values of hasPart, False: Don't create duplicates
        """
        if allow_duplicates or self.get_element_with_value("dcterms:hasPart", value) is None:
            self.add_element_with_value("dcterms:hasPart", value)

    def remove_parts(self, value=None, just_first=True):
        """
        Remove a dcterms:hasPart element that matches value or otherwise all dcterms:hasPart elements if value is None
        :param value: Value to remove or None (to remove all values)
        :param just_first: Boolean - True: Remove max of 1 <dcterms:hasPart> element;
                                     False: Remove all <dcterms:hasPart> elements that match value
        """
        if value:
            self.delete_elements_matching_value("dcterms:hasPart", value, just_first=just_first)
        else:
            # Delete ALL hasPart elements
            self._get_qualified_tagname_and_delete_elements_matching_tagname("dcterms:hasPart")

    @property
    def has_version(self):
        return self.get_elements_list("dcterms:hasVersion", True)

    @has_version.setter
    def has_version(self, values):
        """
        :param values: String list hasVersion text - can be singular
        """
        self.set_elements_with_values_list("dcterms:hasVersion", values)

    @property
    def id(self):
        return self.get_element("atom:id", True)

    @id.setter
    def id(self, value):
        """
        :param value: String ID
        """
        self.set_element_with_value("atom:id", value)

    @property
    def identifier(self):
        return self.get_elements_list("dcterms:identifier", True)

    @identifier.setter
    def identifier(self, values):
        """
        :param values: String list of identifiers - can be singular
        """
        self.set_elements_with_values_list("dcterms:identifier", values)

    @property
    def is_part_of(self):
        return self.get_elements_list("dcterms:isPartOf", True)

    @is_part_of.setter
    def is_part_of(self, values):
        """
        :param values: String list of isPartOf data - can be singular
        """
        self.set_elements_with_values_list("dcterms:isPartOf", values)

    @property
    def publishers(self):
        return self.get_elements_list("dcterms:publisher", True)

    @publishers.setter
    def publishers(self, values):
        """
        :param values: String publisher value
        """
        self.set_elements_with_values_list("dcterms:publisher", values)

    @property
    def references(self):
        return self.get_elements_list("dcterms:references", True)

    @references.setter
    def references(self, values):
        """
        :param values: String list of references - can be singular
        """
        self.set_elements_with_values_list("dcterms:references", values)

    @property
    def rights_holder(self):
        return self.get_element("dcterms:rightsHolder", True)

    @rights_holder.setter
    def rights_holder(self, value):
        """
        :param value: String rights holder value
        """
        self.set_element_with_value("dcterms:rightsHolder", value)

    @property
    def source(self):
        return self.get_element("dcterms:source", True)

    @source.setter
    def source(self, value):
        """
        :param value: String source value
        """
        self.set_element_with_value("dcterms:source", value)

    @property
    def summary(self):
        return self.get_element("atom:summary", True)

    @summary.setter
    def summary(self, value):
        """
        :param value: String summary text
        """
        self.set_element_with_value("atom:summary", value)

    @property
    def type(self):
        return self.get_element("dcterms:type", True)

    @type.setter
    def type(self, value):
        """
        :param value: String type text
        """
        self.set_element_with_value("dcterms:type", value)

    @property
    def updated(self):
        return self.get_element("atom:updated", True)

    @updated.setter
    def updated(self, value):
        """
        :param value: String updated text
        """
        self.set_element_with_value("atom:updated", value)

    @property
    def format(self):
        return self.get_elements_list("dcterms:format", True)

    @format.setter
    def format(self, values):
        self.set_elements_with_values_list("dcterms:format", values)

    @property
    def language(self):
        return self.get_elements_list("dcterms:language", True)

    @language.setter
    def language(self, values):
        self.set_elements_with_values_list("dcterms:language", values)

    @property
    def subject(self):
        return self.get_elements_list("dcterms:subject", True)

    @subject.setter
    def subject(self, values):
        self.set_elements_with_values_list("dcterms:subject", values)

    @property
    def medium(self):
        return self.get_element("dcterms:medium", True)

    @medium.setter
    def medium(self, value):
        self.set_element_with_value("dcterms:medium", value)

    @property
    def date_accepted(self):
        return self.get_element("dcterms:dateAccepted", True)

    @date_accepted.setter
    def date_accepted(self, value):
        self.set_element_with_value("dcterms:dateAccepted", value)

    @property
    def date_submitted(self):
        return self.get_element("dcterms:dateSubmitted", True)

    @date_submitted.setter
    def date_submitted(self, value):
        self.set_element_with_value("dcterms:dateSubmitted", value)


class Feed(SwordModel):

    _root = SwordModel.tagname_to_namespaced_tagname("atom:feed")

    _namespaces = {
        None: "http://www.w3.org/2005/Atom",
        # "dcterms": "http://purl.org/dc/terms/",
        "sword": "http://purl.org/net/sword/terms/"
    }

    @property
    def entries(self):
        return [Entry(entry) for entry in self.get_elements_list("atom:entry")]

    @entries.setter
    def entries(self, values):
        """
        List of Entry model objects or Etree instances
        """
        self.set_elements_with_xml_instance_list("atom:entry", values)

    @property
    def links(self):
        return [Link(link) for link in self.get_elements_list("atom:link")]

    @links.setter
    def links(self, values):
        """
        :param values: List of Link model objects or Etree instances
        """
        self.set_elements_with_xml_instance_list("atom:link", values)

    @property
    def authors(self):
        return self.get_elements_list("atom:author")

    @authors.setter
    def authors(self, values):
        """
        :param values: Author element tree instances or SwordModel instances - can be singular
        """
        self.set_elements_with_xml_instance_list("atom:author", values)

    @property
    def id(self):
        return self.get_element("atom:id", True)

    @id.setter
    def id(self, value):
        """
        :param value: String ID
        """
        self.set_element_with_value("atom:id", value)

    @property
    def title(self):
        return self.get_element("atom:title", True)

    @title.setter
    def title(self, value):
        """
        :param value: String title text (atom:title)
        """
        self.set_element_with_value("atom:title", value)

    @property
    def updated(self):
        return self.get_element("atom:updated", True)

    @updated.setter
    def updated(self, value):
        """
        :param value: String updated text
        """
        self.set_element_with_value("atom:updated", value)

    @property
    def description(self):
        return self.get_element("sword:verboseDescription", True)

    @description.setter
    def description(self, value):
        """
        :param value: String verbose description text
        """
        self.set_element_with_value("sword:verboseDescription", value)


class Link(SwordModel):

    _root = SwordModel.tagname_to_namespaced_tagname("atom:link")

    @property
    def rel(self):
        return self.xml.get("rel")

    @rel.setter
    def rel(self, value):
        """
        :param value: String rel value (usually what type of link it is like 'edit' for the EDIT-IRI)
        """
        self.xml.set("rel", value)

    @property
    def href(self):
        return self.xml.get("href")

    @href.setter
    def href(self, value):
        """
        :param value: String link location
        """
        self.xml.set("href", value)

    @property
    def mimetype(self):
        return self.xml.get("type")

    @mimetype.setter
    def mimetype(self, value):
        """
        :param value: String mimetype
        """
        self.xml.set("type", value)


class DepositReceipt(Entry):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._location = None
        
    @property
    def location(self):
        """
        This is a property used to avoid needing to return the Location header of a SWORD2 response
        by itself.

        This will simply be the Location header from a given SWORD2 response.
        """
        return self._location

    @location.setter
    def location(self, value):
        """
        :param value: Location header value
        """
        self._location = value

    @property
    def links(self):
        return [Link(link) for link in self.get_elements_list("atom:link")]

    @links.setter
    def links(self, values):
        """
        :param values: List of Link model objects or Etree instances
        """
        self.set_elements_with_xml_instance_list("atom:link", values)

    @property
    def packaging(self):
        return self.get_elements_list("sword:packaging", True)

    def get_link_by_xpath(self, rel):
        """
        Simple XPATH link retrieval

        XPATH is different from normal ETree find in that it needs listed namespaces to work - so just use the
        normal set of sword namespaces.

        It also needs to use an actually namespaced version of the tagname, so use atom:link instead of a construction.

        :param rel: value of the 'rel' attribute we are searching for with the links.

        :return: The 'href' attribute of the link if found, otherwise None.
        """
        links = self.xpath(f'./atom:link[@rel="{rel}"]')
        return links[0].get("href") if links else None

    @property
    def edit_iri(self):
        return self.get_link_by_xpath("edit")

    @property
    def em_iri(self):
        return self.get_link_by_xpath("edit-media")

    @property
    def se_iri(self):
        return self.get_link_by_xpath("http://purl.org/net/sword/terms/add")

    @property
    def treatment(self):
        return self.get_element("sword:treatment", True)

    @treatment.setter
    def treatment(self, value):
        """
        :param value: String treatment text
        """
        self.set_element_with_value("sword:treatment", value)

    @property
    def verbose_description(self):
        return self.get_element("sword:verboseDescription", True)

    @verbose_description.setter
    def verbose_description(self, value):
        """
        :param value: String verbose description text
        """
        self.set_element_with_value("sword:verboseDescription", value)


class ErrorDocument(DepositReceipt):

    """
    Model for a <sword:error> element

    This is simply a deposit receipt with a couple of extra sword tags.
    """

    _root = SwordModel.tagname_to_namespaced_tagname("sword:error")

    # So users of the client know there was an error easily
    def is_error(self):
        return True

    @property
    def summary(self):
        return self.get_element("atom:summary", True)

    @summary.setter
    def summary(self, value):
        """
        :param value: String summary text
        """
        self.set_element_with_value("atom:summary", value)

    @property
    def verbose(self):
        return self.get_element("sword:verboseDescription", True)

    @verbose.setter
    def verbose(self, value):
        """
        :param value: String verbose text
        """
        self.set_element_with_value("sword:verboseDescription", value)
