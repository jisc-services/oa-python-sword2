"""
Authentication classes for use with the SWORD2 server.

SwordAuthenticationBase should be extended and used to the developer's own liking.
"""
from flask import request, current_app

from sword2.server.util import atom_error, raise_not_implemented_error_for_method
from sword2.server.globals import messages


class SwordAuthenticationBase:

    raise_not_implemented_error = raise_not_implemented_error_for_method

    @classmethod
    def unauthenticated(cls):
        """
        Base auth for sword - when unauthenticated, sends a 401 with an atom error document.
        """
        atom_error(messages.NOT_AUTHED_ERROR, 401)

    @classmethod
    def valid_credentials(cls, auth):
        """
        Should return a boolean or object which determines whether the credentials are valid or not.

        :param auth: Flask request authorization object - basic auth.

        :return: Falsy value if unauthenticated, truthy value if authenticated.
        So, you could return True/False or Account details/None.
        """
        cls.raise_not_implemented_error("valid_credentials")

    @classmethod
    def authenticate(cls, collection_id=None, container_id=None):
        """
        Simple authentication function that doesn't test auth by collection or container.
        The parameters can be used in a customized implementation however.

        :param collection_id: Collection we are trying to authenticate with
        :param container_id: Container we are trying to authenticate with

        :return: If unauthenticated, possibly throw an error or return an error object. If authenticated, return None.
        """
        auth = request.authorization
        response = None
        if not auth or not cls.valid_credentials(auth):
            response = cls.unauthenticated()
        return response


class SwordNoAuthentication(SwordAuthenticationBase):
    # just returns True whenever asked for authentication

    @classmethod
    def valid_credentials(cls, auth):
        return True

    @classmethod
    def authenticate(cls, *args, **kwargs):
        return True


class SwordBasicAuthentication(SwordAuthenticationBase):

    @classmethod
    def valid_credentials(cls, auth):
        """
        Very simple Basic Auth implementation for testing.
        Uses the flask auth object to get the auth username and password.

        :param auth: Flask authorization object like parent class

        :return: Whether the username and password is stored or not
        """
        password = current_app.config.get("USERS").get(auth.username)
        return password == auth.password
