class RepositoryError(Exception):
    """
    Simple error class for repositories, custom message will be used in error throwing if
    one of these is thrown in a repository implementation.
    """

    def __init__(self, message, verbose_msg=None, status_code=500, log_level=None, log_msg=None):
        """
        Set the error message and status_code. Default for status_code is 500.

        :param message: String - Message to show in the error
        :param verbose_msg: String - OPTIONAL long description of error to show in the error
        :param status_code: Integer - Status code to use when returning the error response
        :param log_level: String or Int - Level of logging required (or None for no logging)
        :param log_msg: String - Particular message to write to log
        """
        self.message = message
        self.verbose_msg = verbose_msg
        self.status_code = status_code
        self.log_level = log_level
        self.log_msg = log_msg
