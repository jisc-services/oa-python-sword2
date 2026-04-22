"""
Messages file - creates user specific messages.
"""
from flask import current_app


class Messages:

    NO_FILE_ERROR = "The request was missing a file."
    DATA_WAS_NOT_XML_ERROR = "The received metadata was not a properly formatted ATOM XML document, or was empty."
    DID_NOT_FIND_FILE_ERROR = "The file '{}' requested did not exist."
    UNKNOWN_ERROR = "An unexpected error occurred."
    NOT_AUTHED_ERROR = "You are not authenticated. Please authenticate."
    IN_PROGRESS = "The deposit is currently in progress."
    DEPOSIT_COMPLETE = "The deposit is now completed."
    BAD_MULTIPART_ERROR = "The multipart request was missing either the 'atom' file or the 'payload' file."
    ATOM_ERROR = "Could not find deposit with id {} in collection {}"
    NO_COLLECTION_ERROR = "The requested collection does not exist"

    def __init__(self):
        """
        The init method has defaults if we can't get anything from the current_app.

        This should only be used in an app context.
        """
        self.NO_FILE_ERROR = current_app.config.get("NO_FILE_ERROR", self.NO_FILE_ERROR)
        self.DATA_WAS_NOT_XML_ERROR = current_app.config.get("DATA_WAS_NOT_XML_ERROR", self.DATA_WAS_NOT_XML_ERROR)
        self.DID_NOT_FIND_FILE_ERROR = current_app.config.get("DID_NOT_FIND_FILE_ERROR", self.DID_NOT_FIND_FILE_ERROR)
        self.UNKNOWN_ERROR = current_app.config.get("UNKNOWN_ERROR", self.UNKNOWN_ERROR)
        self.NOT_AUTHED_ERROR = current_app.config.get("NOT_AUTHED_ERROR", self.NOT_AUTHED_ERROR)
        self.IN_PROGRESS = current_app.config.get("IN_PROGRESS", self.IN_PROGRESS)
        self.DEPOSIT_COMPLETE = current_app.config.get("DEPOSIT_COMPLETE", self.DEPOSIT_COMPLETE)
        self.BAD_MULTIPART_ERROR = current_app.config.get("BAD_MULTIPART_ERROR", self.BAD_MULTIPART_ERROR)
        self.ATOM_ERROR = current_app.config.get("ATOM_ERROR", self.ATOM_ERROR)
        self.NO_COLLECTION_ERROR = current_app.config.get("NO_COLLECTION_ERROR", self.NO_COLLECTION_ERROR)
