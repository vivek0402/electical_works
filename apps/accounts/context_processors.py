from .roles import ADMIN, OFFICE, TECHNICIAN, has_role


def roles(request):
    """Role flags for templates (navigation only; views enforce access themselves)."""
    user = request.user
    return {
        "is_admin": has_role(user, ADMIN),
        "is_office": has_role(user, OFFICE),
        "is_technician": has_role(user, TECHNICIAN),
    }
