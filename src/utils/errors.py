class KaspaError(Exception):
    pass


class APIError(KaspaError):
    pass


class DatabaseError(KaspaError):
    pass


class InputError(KaspaError):
    pass
