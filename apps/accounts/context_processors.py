from .roles import ADMIN, has_role


def roles(request):
    return {"is_admin": has_role(request.user, ADMIN)}
